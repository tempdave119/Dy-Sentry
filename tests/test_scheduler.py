"""调度器单测（离线，注入假 fetch 与假时钟）。"""
import asyncio

from config.store import ConfigStore
from schedule.scheduler import Scheduler


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, secs):
        self.now += secs


def _store(tmp_path, rooms_yaml=""):
    if rooms_yaml:
        (tmp_path / "rooms.yaml").write_text(rooms_yaml, encoding="utf-8")
    (tmp_path / "config.yaml").write_text("poll_interval: 10\n", encoding="utf-8")
    return ConfigStore(
        config_path=str(tmp_path / "config.yaml"),
        rooms_path=str(tmp_path / "rooms.yaml"),
    )


def _run(coro):
    return asyncio.run(coro)


def test_per_room_intervals(tmp_path):
    store = _store(tmp_path, (
        "rooms:\n"
        "  - id: A\n    url: https://x/A\n    enabled: true\n"
        "  - id: B\n    url: https://x/B\n    enabled: true\n    poll_schedule: '00:00-23:59=100'\n"
    ))
    clock = FakeClock()
    calls = {"A": 0, "B": 0}

    async def fetch(url, quality, cookie):
        calls[url.rsplit("/", 1)[-1]] += 1
        return {"is_live": False}

    sch = Scheduler(store, fetch=fetch, jitter=0, now_fn=clock, minutes_fn=lambda: 720)
    _run(sch._tick())            # 首轮：A、B 都到期
    assert calls == {"A": 1, "B": 1}

    clock.advance(10)
    _run(sch._tick())            # A(10s) 到期，B(100s) 未到期
    assert calls == {"A": 2, "B": 1}

    clock.advance(90)
    _run(sch._tick())            # 累计 100s：B 到期
    assert calls == {"A": 3, "B": 2}


def test_live_hooks_fire_on_transition(tmp_path):
    store = _store(tmp_path, "rooms:\n  - id: A\n    url: https://x/A\n    enabled: true\n")
    clock = FakeClock()
    live = [True]
    events = []

    async def fetch(url, quality, cookie):
        return {"is_live": live[0], "anchor_name": "n"}

    async def on_live(room, info):
        events.append("live")

    async def on_offline(room, info):
        events.append("offline")

    sch = Scheduler(store, fetch=fetch, on_live=on_live, on_offline=on_offline,
                    jitter=0, now_fn=clock, minutes_fn=lambda: 720)
    _run(sch._tick())            # 开播 → on_live
    assert events == ["live"]
    clock.advance(10)
    _run(sch._tick())            # 仍开播 → 不重复触发
    assert events == ["live"]
    live[0] = False
    clock.advance(10)
    _run(sch._tick())            # 下播 → on_offline
    assert events == ["live", "offline"]


def test_error_backoff_increases_interval(tmp_path):
    store = _store(tmp_path, "rooms:\n  - id: A\n    url: https://x/A\n    enabled: true\n")
    clock = FakeClock()

    async def fetch(url, quality, cookie):
        raise RuntimeError("boom")

    sch = Scheduler(store, fetch=fetch, jitter=0, now_fn=clock, minutes_fn=lambda: 720)
    _run(sch._tick())
    st = sch.state["https://x/A"]
    assert st.error_count == 1
    first = st.interval                 # 无错误时的基线间隔
    second = sch.effective_interval(store.rooms[0])   # 有 1 次错误 → 翻倍
    assert st.error_count == 1
    assert second > first               # 退避：间隔增大
    assert second == first * 2


def test_disabled_room_not_polled(tmp_path):
    store = _store(tmp_path, "rooms:\n  - id: A\n    url: https://x/A\n    enabled: false\n")
    clock = FakeClock()
    calls = []

    async def fetch(url, quality, cookie):
        calls.append(url)
        return {"is_live": False}

    sch = Scheduler(store, fetch=fetch, jitter=0, now_fn=clock, minutes_fn=lambda: 720)
    _run(sch._tick())
    assert calls == []


def test_hot_reload_adds_room(tmp_path):
    store = _store(tmp_path, "rooms:\n  - id: A\n    url: https://x/A\n    enabled: true\n")
    clock = FakeClock()
    calls = []

    async def fetch(url, quality, cookie):
        calls.append(url.rsplit("/", 1)[-1])
        return {"is_live": False}

    sch = Scheduler(store, fetch=fetch, jitter=0, now_fn=clock, minutes_fn=lambda: 720)
    _run(sch._tick())
    assert calls == ["A"]

    (tmp_path / "rooms.yaml").write_text(
        "rooms:\n  - id: A\n    url: https://x/A\n    enabled: true\n"
        "  - id: B\n    url: https://x/B\n    enabled: true\n", encoding="utf-8")
    import os
    os.utime(tmp_path / "rooms.yaml", (9e9, 9e9))
    clock.advance(10)
    _run(sch._tick())            # 热重载后 B 加入并被轮询
    assert "B" in calls


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
