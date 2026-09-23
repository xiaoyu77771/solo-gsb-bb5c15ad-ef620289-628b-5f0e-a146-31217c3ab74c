import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# 并发测试使用独立的临时文件型 SQLite（:memory: 无法跨连接共享）
_tmp_dir = tempfile.mkdtemp(prefix="coldchain-concurrency-")
os.environ["COLDCHAIN_DATABASE_URL"] = f"sqlite:///{_tmp_dir}/concurrency.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)

PAYLOAD = {
    "boxCode": "BOX-CONC",
    "seq": 1,
    "temperature": 3.3,
    "eventTime": "2026-09-23T03:00:00Z",
}


def _post(_):
    # 每个线程使用独立的 TestClient，避免共享 httpx 连接
    with TestClient(app) as c:
        r = c.post("/api/v1/events", json=PAYLOAD)
        return r.status_code, r.json()


def test_concurrent_identical_retries_exactly_one_insert():
    n = 10
    results = []
    with ThreadPoolExecutor(max_workers=n) as pool:
        futures = [pool.submit(_post, i) for i in range(n)]
        for f in as_completed(futures):
            results.append(f.result())

    statuses = [code for code, _ in results]
    # 恰好一次 201，其余全部按幂等重复处理（200），没有 409/500
    assert statuses.count(201) == 1
    assert statuses.count(200) == n - 1

    for code, body in results:
        if code == 200:
            assert body["duplicate"] is True

    # 数据库中只有一条
    r = client.get("/api/v1/boxes/BOX-CONC/events")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_concurrent_different_payloads_one_wins_rest_conflict():
    barrier = threading.Barrier(2)

    def post_temp(temp):
        barrier.wait()  # 尽量让两个 INSERT 同时发出
        with TestClient(app) as c:
            r = c.post(
                "/api/v1/events",
                json={
                    "boxCode": "BOX-RACE",
                    "seq": 1,
                    "temperature": temp,
                    "eventTime": "2026-09-23T03:00:00Z",
                },
            )
            return r.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(post_temp, [1.0, 2.0]))

    assert sorted(codes) == [201, 409]

    # 胜者状态确定且唯一
    r = client.get("/api/v1/boxes/BOX-RACE/events")
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["temperature"] in (1.0, 2.0)
