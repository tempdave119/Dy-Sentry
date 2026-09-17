"""DanmakuRecorder 落盘单测（桩掉 iter_danmaku，不触网）。"""
import asyncio
import json

import capture.danmaku_recorder as dr_mod
from capture.danmaku_recorder import DanmakuRecorder


def _fake_messages():
    async def gen(room_id, **kw):
        for i in range(3):
            yield {"type": "chat", "user": f"u{i}", "content": f"m{i}", "ts": 1}
    return gen


def test_writes_jsonl_and_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(dr_mod, "iter_danmaku", _fake_messages())
    out = tmp_path / "a" / "d.jsonl"

    async def run():
        rec = DanmakuRecorder("123", out, anchor="A", title="T")
        await rec.start()
        await asyncio.sleep(0.3)
        summary = await rec.stop()
        return rec, summary

    rec, summary = asyncio.run(run())
    lines = out.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    assert json.loads(lines[0])["content"] == "m0"
    assert rec.count == 3
    assert rec.by_type == {"chat": 3}
    text = summary.read_text(encoding="utf-8")
    assert "total: 3" in text and "chat: 3" in text and "anchor: A" in text


def test_stop_without_start_safe(tmp_path):
    async def run():
        rec = DanmakuRecorder("1", tmp_path / "none.jsonl")
        assert rec.is_running is False
        assert await rec.stop() is None
    asyncio.run(run())


if __name__ == "__main__":
    import pathlib
    import tempfile

    class MP:
        def __init__(self): self._old = []
        def setattr(self, obj, name, val):
            self._old.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)
        def undo(self):
            for obj, name, val in self._old: setattr(obj, name, val)

    failed = 0
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        mp = MP()
        with tempfile.TemporaryDirectory() as td:
            try:
                fn(pathlib.Path(td), mp)
                print(f"PASS {fn.__name__}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {fn.__name__}: {e}")
        mp.undo()
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
