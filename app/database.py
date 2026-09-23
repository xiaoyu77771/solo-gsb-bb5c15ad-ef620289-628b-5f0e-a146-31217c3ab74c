import os
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
    url = settings.database_url
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["timeout"] = 30  # 并发写入时等待锁的秒数
        # 确保 SQLite 文件所在目录存在
        db_path = url.removeprefix("sqlite:///").removeprefix("sqlite://")
        if db_path and db_path != ":memory:":
            db_dir = os.path.dirname(os.path.abspath(db_path))
            os.makedirs(db_dir, exist_ok=True)

    engine = create_engine(
        url,
        connect_args=connect_args,
        # SQLite 多线程/多连接下用 WAL 降低读写互斥
        pool_pre_ping=not url.startswith("sqlite"),
    )

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """创建数据表（首次启动自动调用，幂等）。"""
    import app.models  # noqa: F401  确保模型已注册

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每请求一个数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
