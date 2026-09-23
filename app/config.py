from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """服务配置，均可通过环境变量覆盖（大小写不敏感）。"""

    model_config = SettingsConfigDict(
        env_prefix="COLDCHAIN_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # SQLite: sqlite:///./data/coldchain.db（容器内默认绝对路径）
    # PostgreSQL 示例: postgresql+psycopg://user:pass@db:5432/coldchain
    database_url: str = Field(
        default="sqlite:////data/coldchain.db",
        description="SQLAlchemy 数据库连接串",
    )

    host: str = Field(default="0.0.0.0", description="HTTP 监听地址")
    port: int = Field(default=8000, description="HTTP 监听端口")

    min_temperature: float = Field(
        default=-60.0, description="允许上报的最低温度（摄氏度，含边界）"
    )
    max_temperature: float = Field(
        default=85.0, description="允许上报的最高温度（摄氏度，含边界）"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
