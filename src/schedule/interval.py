"""分时段轮询间隔解析（痛点2 核心）。移植自 DANMU:src/config.py 的 resolve_schedule_interval。

配置格式: "08:00-20:00=300, 22:00-06:00=30"
含义: 08:00~20:00 每 300 秒轮询, 22:00~次日06:00 每 30 秒, 其余用 default。
支持跨天时段；多个时段首个匹配优先。
"""
from __future__ import annotations

import time


def current_minutes(now: time.struct_time | None = None) -> int:
    t = now or time.localtime()
    return t.tm_hour * 60 + t.tm_min


def resolve_schedule_interval(
    schedule_str: str,
    default_interval: int,
    now_minutes: int | None = None,
) -> int:
    """按分时段配置返回当前应使用的轮询间隔（秒）；未命中返回 default_interval。"""
    schedule_str = (schedule_str or "").strip()
    if not schedule_str:
        return default_interval

    if now_minutes is None:
        now_minutes = current_minutes()

    for slot in schedule_str.split(","):
        slot = slot.strip()
        if not slot or "=" not in slot:
            continue
        try:
            time_range, interval_str = slot.rsplit("=", 1)
            interval = int(interval_str.strip())
            start_str, end_str = time_range.strip().split("-")
            sh, sm = map(int, start_str.strip().split(":"))
            eh, em = map(int, end_str.strip().split(":"))
            start_min = sh * 60 + sm
            end_min = eh * 60 + em

            if start_min <= end_min:
                if start_min <= now_minutes < end_min:
                    return interval
            else:  # 跨天时段
                if now_minutes >= start_min or now_minutes < end_min:
                    return interval
        except (ValueError, IndexError):
            continue

    return default_interval


def room_interval(
    room: dict,
    global_schedule: str,
    default_interval: int,
    now_minutes: int | None = None,
) -> int:
    """单个房间的有效轮询间隔。优先级: 房间级 poll_schedule > 全局 poll_schedule > 默认。

    与 DANMU monitor._get_room_interval 一致：房间级时段未命中时回落到 default_interval
    （而非全局时段），保证房间配置语义独立。
    """
    room_schedule = (room.get("poll_schedule") or "").strip()
    if room_schedule:
        return resolve_schedule_interval(room_schedule, default_interval, now_minutes)
    return resolve_schedule_interval(global_schedule, default_interval, now_minutes)
