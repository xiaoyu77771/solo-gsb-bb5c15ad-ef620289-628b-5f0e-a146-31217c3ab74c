import os
import sys
import tempfile

import pytest

# 测试使用独立的临时 SQLite 文件；必须在导入应用之前设置
_tmp_dir = tempfile.mkdtemp(prefix="coldchain-test-")
os.environ["COLDCHAIN_DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base, engine, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    with TestClient(app) as c:
        yield c
