"""API 冒烟单测（离线，不触网）。验证 app 可启动、路由契约正确。

可 pytest 运行，也可 `PYTHONPATH=src python3 tests/test_api_smoke.py`。
"""
from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)


def test_index_serves_player_page():
    r = client.get("/")
    assert r.status_code == 200
    assert "mpegts" in r.text


def test_vendor_mpegts_self_hosted():
    r = client.get("/vendor/mpegts.js")
    assert r.status_code == 200
    assert "mpegts" in r.text


def test_index_has_no_external_cdn():
    html = client.get("/").text
    assert "cdn.jsdelivr" not in html
    assert "/vendor/mpegts.js" in html


def test_status_rejects_non_dy_url():
    r = client.get("/api/status", params={"url": "https://example.com/x"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_live"] is False
    assert "error" in body


def test_preview_conflict_when_not_live():
    r = client.get("/api/preview", params={"url": "https://example.com/x"})
    assert r.status_code == 409
    assert r.json()["error"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
