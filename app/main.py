from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.routers import boxes, errors, events
from app.schemas import HealthOut


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 启动时自动建表、初始化依赖数据结构
    init_db()
    yield


app = FastAPI(
    title="冷链周转箱事件接收 API",
    description=(
        "接收冷链周转箱温度事件，支持设备重试幂等、乱序上报，"
        "并按序号返回每个箱子的最新状态。"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

errors.register_exception_handlers(app)
app.include_router(events.router)
app.include_router(boxes.router)


@app.get("/health", response_model=HealthOut, tags=["meta"], summary="健康检查")
def health() -> HealthOut:
    return HealthOut(status="ok")


@app.get("/", tags=["meta"], summary="服务简介")
def root() -> dict[str, str]:
    return {
        "service": "cold-chain-box-events",
        "docs": "/docs",
        "health": "/health",
        "api": "/api/v1/events",
    }
