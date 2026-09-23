def _event(seq, temp, ts="2026-09-23T02:00:00Z", box="BOX-001"):
    return {
        "boxCode": box,
        "seq": seq,
        "temperature": temp,
        "eventTime": ts,
    }


def test_create_event_returns_201(client):
    r = client.post("/api/v1/events", json=_event(1, 4.5))
    assert r.status_code == 201
    body = r.json()
    assert body["duplicate"] is False
    assert body["event"]["box_code"] == "BOX-001"
    assert body["event"]["seq"] == 1
    assert body["event"]["temperature"] == 4.5
    # 输出统一为 UTC（Z 或 +00:00 均可）
    assert body["event"]["event_time"].endswith(("Z", "+00:00"))


def test_duplicate_same_content_is_idempotent(client):
    payload = _event(1, 4.5, "2026-09-23T10:00:00+08:00")
    r1 = client.post("/api/v1/events", json=payload)
    assert r1.status_code == 201
    first = r1.json()["event"]

    # 设备重试：完全相同的内容（不同写法的时区代表同一时刻也算相同）
    retry = _event(1, 4.5, "2026-09-23T02:00:00Z")
    r2 = client.post("/api/v1/events", json=retry)
    assert r2.status_code == 200
    second = r2.json()
    assert second["duplicate"] is True
    # received_at 不被更新
    assert second["event"]["received_at"] == first["received_at"]

    # 数据库中只有一条
    r3 = client.get("/api/v1/boxes/BOX-001/events")
    assert len(r3.json()) == 1


def test_same_seq_different_content_conflict(client):
    r1 = client.post("/api/v1/events", json=_event(1, 4.5))
    assert r1.status_code == 201

    # 温度不同
    r2 = client.post("/api/v1/events", json=_event(1, 8.0))
    assert r2.status_code == 409
    assert "序号 1" in r2.json()["detail"]

    # 事件时间不同
    r3 = client.post(
        "/api/v1/events", json=_event(1, 4.5, "2026-09-23T03:00:00Z")
    )
    assert r3.status_code == 409

    # 被拒绝的内容没有污染状态
    state = client.get("/api/v1/boxes/BOX-001").json()
    assert state["state"]["temperature"] == 4.5


def test_out_of_order_events_latest_state_by_seq(client):
    # 乱序写入（3 -> 1 -> 2），每次返回的 state 都是当前最大序号
    for seq, temp in [(3, 6.0), (1, 2.0), (2, 4.0)]:
        r = client.post(
            "/api/v1/events",
            json=_event(seq, temp, f"2026-09-23T0{seq}:00:00Z"),
        )
        assert r.status_code == 201
        assert r.json()["state"]["seq"] == 3

    state = client.get("/api/v1/boxes/BOX-001").json()["state"]
    assert state["seq"] == 3
    assert state["temperature"] == 6.0

    # 迟到的更小序号入库，不改变最新状态
    r = client.post(
        "/api/v1/events", json=_event(0, 1.0, "2026-09-23T00:00:00Z")
    )
    assert r.status_code == 201
    assert r.json()["state"]["seq"] == 3


def test_list_all_boxes_latest_states(client):
    client.post("/api/v1/events", json=_event(1, 4.0, box="BOX-A"))
    client.post("/api/v1/events", json=_event(2, 5.0, box="BOX-A"))
    client.post("/api/v1/events", json=_event(10, -2.0, box="BOX-B"))
    client.post(
        "/api/v1/events",
        json=_event(5, 9.0, box="BOX-B", ts="2026-09-23T05:00:00Z"),
    )

    boxes = client.get("/api/v1/boxes").json()
    by_code = {b["box_code"]: b["state"] for b in boxes}
    assert by_code["BOX-A"]["seq"] == 2
    assert by_code["BOX-B"]["seq"] == 10
    assert by_code["BOX-B"]["temperature"] == -2.0


def test_box_code_normalized_and_validation(client):
    # 小写 + 首尾空白会被规范化
    r = client.post(
        "/api/v1/events", json=_event(1, 4.0, box="  box-007  ")
    )
    assert r.status_code == 201
    assert r.json()["event"]["box_code"] == "BOX-007"

    # 非法字符
    r = client.post("/api/v1/events", json=_event(1, 4.0, box="BOX/001"))
    assert r.status_code == 422

    # 温度超范围
    r = client.post("/api/v1/events", json=_event(2, 999.0))
    assert r.status_code == 422

    # 多余字段
    r = client.post(
        "/api/v1/events", json={**_event(3, 4.0), "extra": 1}
    )
    assert r.status_code == 422


def test_unknown_box_returns_404(client):
    r = client.get("/api/v1/boxes/NOPE")
    assert r.status_code == 404


def test_event_history_ordered_by_seq(client):
    for seq in [5, 1, 3, 2, 4]:
        client.post(
            "/api/v1/events",
            json=_event(seq, float(seq), f"2026-09-23T0{seq}:00:00Z"),
        )
    rows = client.get("/api/v1/boxes/BOX-001/events").json()
    assert [e["seq"] for e in rows] == [1, 2, 3, 4, 5]


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
