"""房间 CRUD + 监控状态 API 冒烟单测（离线，临时配置目录）。"""
from fastapi.testclient import TestClient

from api.app import build_app


def _client(tmp_path):
    app = build_app(
        config_path=str(tmp_path / "config.yaml"),
        rooms_path=str(tmp_path / "rooms.yaml"),
    )
    return TestClient(app)


def test_room_crud_and_status(tmp_path):
    c = _client(tmp_path)

    r = c.post("/api/rooms", json={"url": "https://live.dy.example/1001", "name": "R1"})
    assert r.status_code == 201
    rid = r.json()["id"]

    r = c.get("/api/rooms")
    assert [x["id"] for x in r.json()] == [rid]

    # 重复添加 → 409
    r = c.post("/api/rooms", json={"url": "https://live.dy.example/1001"})
    assert r.status_code == 409

    # 修改分时段调度与启用状态
    r = c.patch(f"/api/rooms/{rid}", json={"poll_schedule": "20:00-22:00=15", "enabled": False})
    assert r.status_code == 200
    assert r.json()["poll_schedule"] == "20:00-22:00=15"
    assert r.json()["enabled"] is False

    # 状态快照反映房间
    r = c.get("/api/monitor/status")
    snap = r.json()
    assert len(snap) == 1
    assert snap[0]["id"] == rid
    assert snap[0]["enabled"] is False
    assert snap[0]["is_live"] is False

    # 删除
    assert c.delete(f"/api/rooms/{rid}").status_code == 200
    assert c.delete(f"/api/rooms/{rid}").status_code == 404
    assert c.get("/api/rooms").json() == []


def test_patch_unknown_room_404(tmp_path):
    c = _client(tmp_path)
    assert c.patch("/api/rooms/nope", json={"enabled": True}).status_code == 404


if __name__ == "__main__":
    import pathlib
    import tempfile

    failed = 0
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        with tempfile.TemporaryDirectory() as td:
            try:
                fn(pathlib.Path(td))
                print(f"PASS {fn.__name__}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
