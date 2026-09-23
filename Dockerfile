FROM python:3.12-slim

# 不生成 .pyc、不缓冲输出，便于容器内看日志
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 先装依赖，利用 Docker 层缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝应用代码
COPY app ./app

# SQLite 数据持久化目录（compose 会挂载卷；PostgreSQL 时可忽略）
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# 容器启动：uvicorn 拉起服务；lifespan 中自动建表完成初始化
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
