"""video_recorder 纯逻辑单测（不需要 ffmpeg 二进制）。"""
from capture.video_recorder import (
    build_ffmpeg_cmd,
    build_remux_cmd,
    choose_container,
    get_codec,
)

FLV_URL = "https://pull-flv.example/live.flv?codec=h264"
H265_URL = "https://pull-flv.example/live.flv?codec=h265"


def test_get_codec():
    assert get_codec(H265_URL) == "h265"
    assert get_codec(FLV_URL) == "h264"
    assert get_codec("https://x/live.flv") is None


def test_choose_container_h265_falls_back_to_ts():
    assert choose_container(H265_URL, prefer="flv") == "ts"
    assert choose_container(FLV_URL, prefer="flv") == "flv"
    assert choose_container(FLV_URL, prefer="ts") == "ts"


def test_build_ffmpeg_cmd_basics():
    cmd = build_ffmpeg_cmd(FLV_URL, "/tmp/out.flv")
    assert cmd[0] == "ffmpeg"
    assert "-c" in cmd and cmd[cmd.index("-c") + 1] == "copy"   # 不转码
    assert "-i" in cmd and cmd[cmd.index("-i") + 1] == FLV_URL
    assert cmd[-1] == "/tmp/out.flv"
    assert cmd[cmd.index("-f") + 1] == "flv"


def test_headers_inserted_before_input():
    cmd = build_ffmpeg_cmd(FLV_URL, "/tmp/out.flv", cookie="ttwid=abc", referer="https://r/")
    hi = cmd.index("-headers")
    ii = cmd.index("-i")
    assert hi < ii                      # -headers 必须在 -i 之前
    hdr = cmd[hi + 1]
    assert "Cookie: ttwid=abc" in hdr and "Referer: https://r/" in hdr


def test_no_headers_when_no_cookie_or_referer():
    cmd = build_ffmpeg_cmd(FLV_URL, "/tmp/out.flv")
    assert "-headers" not in cmd


def test_segment_split_variant():
    cmd = build_ffmpeg_cmd(FLV_URL, "/tmp/out.flv", segment_seconds=600)
    assert cmd[cmd.index("-f") + 1] == "segment"
    assert "-segment_time" in cmd and "600" in cmd
    assert any("_%03d" in a for a in cmd)


def test_build_remux_cmd():
    cmd = build_remux_cmd("/tmp/out.flv", "/tmp/out.mp4")
    assert cmd[0] == "ffmpeg"
    assert "-movflags" in cmd and cmd[cmd.index("-movflags") + 1] == "+faststart"
    assert cmd[-1] == "/tmp/out.mp4"
    assert cmd[cmd.index("-c") + 1] == "copy"   # 无损转封装


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
