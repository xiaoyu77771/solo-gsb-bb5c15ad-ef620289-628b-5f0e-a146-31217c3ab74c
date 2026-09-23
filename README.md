# 冷链周转箱事件接收 API

基于 **Python + FastAPI + SQLAlchemy** 的冷链周转箱温度事件接收服务。设备上报
**箱号、递增序号、温度、事件时间**；服务针对设备网络场景内置以下语义：

| 场景 | 处理方式 | HTTP 状态码 |
| --- | --- | --- |
| 首次收到 `(箱号, 序号)` | 正常入库 | `201 Created` |
| 相同序号 + **相同内容**（设备重试 / 重复投递） | 幂等返回，不重复入库、不改变状态，`received_at` 不变 | `200 OK`（`duplicate=true`） |
| 相同序号 + **内容不同**（温度或事件时间不一致） | 拒绝，返回冲突，状态不被污染 | `409 Conflict` |
| 乱序 / 延迟上报 | 照常入库；最新状态**始终按序号最大值**计算，与到达顺序无关 | `201 Created` |

> 事件时间支持带时区的 ISO 8601（如 `2026-09-23T10:00:00+08:00` / `Z`），
> 服务端统一转为 **UTC** 存储与返回；同一时刻的不同时区写法视为相同内容。

---

## 一、一键启动（Docker Compose，推荐）

前置要求：已安装 Docker 与 Docker Compose v2（`docker compose` 命令）。

```bash
# 在项目根目录（含 docker-compose.yml）执行
docker compose up -d --build
```

该命令会自动完成：

1. 构建镜像并安装 `requirements.txt` 中的全部依赖；
2. 启动 API 容器；
3. 应用启动时自动建表初始化（`box_events`，含 `(box_code, seq)` 唯一约束），无需手动迁移；
4. 通过命名卷 `coldchain-data` 持久化 SQLite 数据库到 `/data/coldchain.db`。

常用运维命令：

```bash
docker compose logs -f api      # 查看日志
docker compose restart api      # 重启
docker compose down             # 停止并删除容器（数据卷保留）
docker compose down -v          # 停止并同时删除数据卷（清空数据）
```

健康检查：

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

## 二、本地开发启动（不用 Docker）

需要 Python 3.11+：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt          # 开发测试可装 requirements-dev.txt

# 使用本地 SQLite 文件（首次运行自动建表）
mkdir -p data
export COLDCHAIN_DATABASE_URL="sqlite:///./data/coldchain.db"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

运行测试：

```bash
pip install -r requirements-dev.txt
pytest -q
```

---

## 三、配置项

所有配置通过环境变量设置，统一使用 `COLDCHAIN_` 前缀；也可复制
`.env.example` 为 `.env` 后修改（本地 uvicorn 运行时自动读取）。

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `COLDCHAIN_HOST` | `0.0.0.0` | HTTP 监听地址 |
| `COLDCHAIN_PORT` | `8000` | 容器内监听端口；宿主机映射端口也由它控制（见 compose） |
| `COLDCHAIN_DATABASE_URL` | `sqlite:////data/coldchain.db` | SQLAlchemy 连接串。SQLite 开箱即用 |
| `COLDCHAIN_MIN_TEMPERATURE` | `-60` | 合法温度下限（℃，含边界） |
| `COLDCHAIN_MAX_TEMPERATURE` | `85` | 合法温度上限（℃，含边界） |

修改宿主机映射端口示例（容器内端口固定 8000）：

```bash
COLDCHAIN_PORT=18000 docker compose up -d --build
# 之后访问 http://localhost:18000
```

### 可选：切换 PostgreSQL

1. 在 `requirements.txt` 中启用 `psycopg[binary]`；
2. 将 `COLDCHAIN_DATABASE_URL` 改为
   `postgresql+psycopg://用户:密码@主机:5432/库名`（建表语句仍由启动流程自动执行）。

---

## 四、API 地址与端口

- **基础地址（Base URL）**：`http://localhost:8000`
- **交互式文档（Swagger UI）**：<http://localhost:8000/docs>
- **ReDoc 文档**：<http://localhost:8000/redoc>
- **OpenAPI Schema**：<http://localhost:8000/openapi.json>

### 接口列表

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/events` | 上报一个事件 |
| `GET` | `/api/v1/boxes` | 所有箱子的最新状态（按序号计算） |
| `GET` | `/api/v1/boxes/{box_code}` | 指定箱子的最新状态 |
| `GET` | `/api/v1/boxes/{box_code}/events?limit=100&offset=0` | 指定箱子的事件历史（按序号升序分页） |
| `GET` | `/health` | 健康检查 |

### 上报请求

请求体（入参字段为驼峰）：

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `boxCode` | string | 是 | 1–64 字符，字母/数字/`-`/`_`；自动去空白并转大写 |
| `seq` | integer | 是 | 非负，箱内严格递增；`(boxCode, seq)` 唯一 |
| `temperature` | number | 是 | 摄氏度，范围 `COLDCHAIN_MIN_TEMPERATURE` ~ `COLDCHAIN_MAX_TEMPERATURE` |
| `eventTime` | string | 是 | ISO 8601 时间，推荐带时区 |

```bash
curl -X POST http://localhost:8000/api/v1/events \
  -H 'Content-Type: application/json' \
  -d '{
    "boxCode": "BOX-001",
    "seq": 1,
    "temperature": 4.5,
    "eventTime": "2026-09-23T10:00:00+08:00"
  }'
```

首次上报返回 `201`：

```json
{
  "event": {
    "box_code": "BOX-001",
    "seq": 1,
    "temperature": 4.5,
    "event_time": "2026-09-23T02:00:00Z",
    "received_at": "2026-09-23T02:00:00.000000Z"
  },
  "duplicate": false,
  "state": { "...": "该箱子当前最新（序号最大）的事件" }
}
```

设备原样重试（或用 `Z` 重新表达同一时刻）返回 `200`，`duplicate` 为 `true`，
不新增记录、不更新 `received_at`；同序号但温度 / 时间不同返回 `409`：

```json
{ "detail": "箱子 BOX-001 的序号 1 已存在但内容不同，事件被拒绝" }
```

查询某箱子最新状态：

```bash
curl http://localhost:8000/api/v1/boxes/BOX-001
# {"box_code":"BOX-001","state":{"box_code":"BOX-001","seq":1,"temperature":4.5,...}}
```

---

## 五、目录结构

```
.
├── app/
│   ├── main.py            # FastAPI 应用、启动时建表
│   ├── config.py          # 环境变量配置（pydantic-settings）
│   ├── database.py        # 引擎 / 会话 / SQLite 优化（WAL、busy_timeout）
│   ├── models.py          # BoxEvent 模型 + (box_code, seq) 唯一约束
│   ├── schemas.py         # 请求 / 响应模型与字段校验
│   ├── services.py        # 幂等入库、冲突判定、按序号取最新状态
│   ├── exceptions.py      # EventConflictError（映射为 HTTP 409）
│   └── routers/
│       ├── events.py      # POST /api/v1/events
│       └── boxes.py       # GET 箱子状态 / 事件历史
├── tests/                 # pytest 用例（幂等 / 冲突 / 乱序 / 规范化等）
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```

## 六、设计说明

- **幂等键**：数据库层面对 `(box_code, seq)` 建唯一约束，业务层先查后写；
  重复请求直接返回已存记录，不产生写入。
- **冲突检测**：仅比较设备负载内容（温度、事件时间）。时间先归一化为 UTC，
  因此 `10:00+08:00` 与 `02:00Z` 不会误判为冲突。
- **乱序安全**：最新状态通过 `ORDER BY seq DESC LIMIT 1`（列表接口用
  `GROUP BY box_code / MAX(seq)` 关联）得出，与入库先后、`event_time` 先后均无关。
- **存储**：默认 SQLite + WAL，适合边缘网关 / 单机部署；连接串可直接切换
  PostgreSQL 以支持更高并发。
