"""fetcher 纯逻辑单测（不触网）。运行需安装项目依赖（导入 fetcher 会 import httpx）。

可 pytest 运行，也可 `PYTHONPATH=src python3 tests/test_fetcher.py`。
"""
import json

from core import fetcher as F


def test_parse_web_rid():
    assert F.parse_web_rid("https://live.douyin.com/123456789") == "123456789"
    assert F.parse_web_rid("https://live.douyin.com/123456789?x=1") == "123456789"
    assert F.parse_web_rid("https://live.douyin.com/?live_web_rid=216618358711") == "216618358711"
    assert F.parse_web_rid("https://live.douyin.com/?room_id=999") == "999"
    assert F.parse_web_rid("https://example.com/1") is None


def test_quality_index():
    assert F.quality_index("OD") == ("OD", 0)
    assert F.quality_index("hd") == ("HD", 2)
    assert F.quality_index(None) == ("OD", 0)


def _room_with_origin():
    origin_main = {
        "hls": "https://h/origin.m3u8",
        "flv": "https://f/origin.flv",
        "sdk_params": json.dumps({"VCodec": "h265"}),
    }
    stream_data = json.dumps({"data": {"origin": {"main": origin_main}}})
    return {"stream_url": {
        "live_core_sdk_data": {"pull_data": {"stream_data": stream_data}},
        "hls_pull_url_map": {"HD": "https://h/hd.m3u8"},
        "flv_pull_url": {"HD": "https://f/hd.flv"},
    }}


def test_prepend_origin():
    room = _room_with_origin()
    F.prepend_origin(room)
    su = room["stream_url"]
    assert list(su["hls_pull_url_map"])[0] == "ORIGIN"
    assert su["flv_pull_url"]["ORIGIN"].endswith("&codec=h265")


def test_build_stream_lists_pads_to_five():
    room = _room_with_origin()
    F.prepend_origin(room)
    flv, m3u8 = F.build_stream_lists(room)
    assert len(flv) == 5 and len(m3u8) == 5
    assert flv[0].startswith("https://f/origin.flv")


def test_select_quality_picks_origin():
    room = _room_with_origin()
    F.prepend_origin(room)
    flv, m3u8 = F.build_stream_lists(room)
    sel = F.select_quality(flv, m3u8, "OD")
    assert sel["quality"] == "OD"
    assert sel["flv_url"].startswith("https://f/origin.flv")


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
