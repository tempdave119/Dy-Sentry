"""分时段轮询间隔解析单测（纯逻辑，离线）。"""
from schedule.interval import resolve_schedule_interval as rsi
from schedule.interval import room_interval

H = lambda h, m=0: h * 60 + m  # noqa: E731


def test_empty_returns_default():
    assert rsi("", 60, now_minutes=H(12)) == 60
    assert rsi(None, 60, now_minutes=H(12)) == 60


def test_within_range():
    assert rsi("08:00-20:00=300", 60, now_minutes=H(12)) == 300


def test_outside_range_returns_default():
    assert rsi("08:00-20:00=300", 60, now_minutes=H(21)) == 60


def test_cross_midnight():
    sched = "22:00-06:00=30"
    assert rsi(sched, 60, now_minutes=H(23)) == 30
    assert rsi(sched, 60, now_minutes=H(3)) == 30
    assert rsi(sched, 60, now_minutes=H(12)) == 60


def test_first_match_wins():
    sched = "08:00-20:00=300, 09:00-10:00=15"
    assert rsi(sched, 60, now_minutes=H(9, 30)) == 300


def test_malformed_slot_skipped():
    sched = "bad=xx, 08:00-20:00=300"
    assert rsi(sched, 60, now_minutes=H(12)) == 300
    assert rsi("nonsense", 60, now_minutes=H(12)) == 60


def test_room_interval_priority():
    # 房间级命中 → 用房间级
    room = {"poll_schedule": "20:00-22:00=15"}
    assert room_interval(room, "08:00-20:00=300", 60, now_minutes=H(21)) == 15
    # 房间级未命中 → 回落默认（不是全局时段）
    assert room_interval(room, "08:00-20:00=300", 60, now_minutes=H(12)) == 60
    # 无房间级 → 用全局时段
    assert room_interval({}, "08:00-20:00=300", 60, now_minutes=H(12)) == 300
    # 全无 → 默认
    assert room_interval({}, "", 60, now_minutes=H(12)) == 60


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
