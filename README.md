# 冷链周转箱事件接收 API

基于 **Python 3.11 + FastAPI + SQLAlchemy 2.0 + SQLite** 的设备温度事件接收服务。
设备会**重试**或**延迟/乱序**上报，服务按以下规则处理：

- **相同箱号 + 相同序号 + 相同内容**（温度、事件时间）→ 判定为设备重试的重复上报，
  幂等返回已有记录（HTTP `200`，`status=duplicate`），**不改变任何状态**。
- **相同箱号 + 相同序号但内容不同** → 拒绝（HTTP `409 Conflict`）。
- **乱序/延迟事件**（序号先到 3 后到 1、中间跳号等）→ 正常入库；
  查询“最新状态”时始终取每个箱子**序号最大**的一条，与到达顺序无关。

## 目录结构

```
.
├── app/
│   ├── __init__.py
│   ├── config.py          # 环境变量配置
│   ├── database.py        # 引擎/会话，启动建表
│   ├── models.py          # BoxEvent 模型，(box_code, seq) 唯一约束
│   ├── schemas.py         # 请求/响应模型与时间归一化
│   ├── services.py        # 幂等去重、冲突判定、最新状态查询
│   └── main.py            # FastAPI 路由
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh   # 容器启动：初始化建表 -> 启动服务
└── requirements.txt
```

## 一键启动（Docker Compose）

```bash
docker compose up -d --build
```

启动过程会自动完成：

1. 基于 `requirements.txt` 在镜像内安装全部依赖；
2. 容器入口脚本 `docker-entrypoint.sh` 创建数据目录并执行建表初始化（幂等）；
3. 启动 uvicorn。

数据持久化在命名卷 `coldchain-data`（容器内 `/app/data`），重启/重建容器不丢数据。

常用命令：

```bash
docker compose logs -f        # 查看日志
docker compose down           # 停止
docker compose down -v        # 停止并删除数据卷（清空数据）
```

## 本地直接运行（不用 Docker）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

首次请求前/启动时会自动创建 SQLite 表（`./data/coldchain.db`）。

## 配置

通过环境变量配置（均有默认值）：

| 环境变量       | 默认值                          | 说明                                       |
| -------------- | ------------------------------- | ------------------------------------------ |
| `DATABASE_URL` | `sqlite:///./data/coldchain.db` | 数据库连接串（SQLAlchemy 格式）            |
| `APP_HOST`     | `0.0.0.0`                       | 监听地址                                   |
| `APP_PORT`     | `8000`                          | 监听端口（Compose 左侧映射端口同样取它）   |

Compose 下可用 `.env` 或临时变量覆盖，例如改宿主端口：

```bash
APP_PORT=9000 docker compose up -d --build
# 此时宿主访问端口为 9000
```

## API 地址与端口

- 服务地址：`http://localhost:8000`（按上面的端口配置调整）
- Swagger 交互文档：<http://localhost:8000/docs>
- ReDoc：<http://localhost:8000/redoc>

## 接口一览

| 方法 | 路径                          | 说明                                   |
| ---- | ----------------------------- | -------------------------------------- |
| GET  | `/health`                     | 健康检查                               |
| POST | `/events`                     | 上报一个事件（幂等，支持设备重试）     |
| GET  | `/states`                     | 所有箱子的最新状态（按最大序号）       |
| GET  | `/boxes`                      | 所有上报过的箱号                       |
| GET  | `/boxes/{box_code}/state`     | 单个箱子的最新状态                     |
| GET  | `/boxes/{box_code}/events`    | 单个箱子的全部事件（按序号升序）       |

### 上报事件

`POST /events`

请求体：

```json
{
  "box_code": "BOX-001",
  "seq": 0,
  "temperature": -4.5,
  "event_time": "2026-09-23T10:00:00+08:00"
}
```

字段说明：

- `box_code`：箱号，非空字符串（≤64 字符）。
- `seq`：该箱递增的事件序号，非负整数；不要求连续，乱序/补报均可。
- `temperature`：摄氏温度，范围 `-100 ~ 100`。
- `event_time`：ISO 8601 时间；**建议带时区**。服务统一换算为 UTC 存储与比较，
  不带时区的时间按 UTC 处理。

响应：

- 首次入库：`201 Created`，`status = "accepted"`
- 重复上报（同序号且温度、事件时间完全一致）：`200 OK`，`status = "duplicate"`
- 同序号内容不一致：`409 Conflict`，响应体带库中已有值与本次值，便于排查
- 参数非法：`422 Unprocessable Entity`
- 查询不存在的箱子：`404 Not Found`

## 使用示例

```bash
# 上报 seq=1
curl -X POST http://localhost:8000/events \
  -H 'Content-Type: application/json' \
  -d '{"box_code":"BOX-001","seq":1,"temperature":-4.5,
       "event_time":"2026-09-23T10:01:00+08:00"}'

# 设备重试：原样重发 -> 200 duplicate，状态不变
curl -X POST http://localhost:8000/events \
  -H 'Content-Type: application/json' \
  -d '{"box_code":"BOX-001","seq":1,"temperature":-4.5,
       "event_time":"2026-09-23T10:01:00+08:00"}'

# 同序号改温度 -> 409 拒绝
curl -X POST http://localhost:8000/events \
  -H 'Content-Type: application/json' \
  -d '{"box_code":"BOX-001","seq":1,"temperature":9.9,
       "event_time":"2026-09-23T10:01:00+08:00"}'

# 乱序补报 seq=0 / seq=2 ... 最新状态始终取最大 seq
curl http://localhost:8000/boxes/BOX-001/state
curl http://localhost:8000/states
```

## 设计说明

- **去重键**：数据库对 `(box_code, seq)` 建唯一约束（`uq_box_seq`）。
  应用层先查后插，且捕获并发下的 `IntegrityError` 重新判定，
  因此设备并发重试也不会产生重复行或错误覆盖。
- **内容相等**：比较 `temperature` 与已归一化为 UTC 的 `event_time`。
  重试通常原样重发 JSON，浮点解析结果一致，可直接判等。
- **乱序安全**：最新状态通过“每箱 `MAX(seq)` 关联回原行”的子查询得到，
  不依赖插入先后，也不要求序号连续。
- **持久化**：默认 SQLite + WAL，卷挂载于 `/app/data`；
  如需 PostgreSQL/MySQL，只需将 `DATABASE_URL` 换成对应 SQLAlchemy 连接串
  （并安装相应驱动），建表逻辑通用。
