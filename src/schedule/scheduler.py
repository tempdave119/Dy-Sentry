"""异步监控调度器（痛点2 执行体）。

单异步事件循环 + 房间注册表（弃用存档的 thread-per-room）。每个房间按
「当前时段的轮询间隔」独立判断是否到期（per-room last_poll）。
借鉴 DLR 的健壮性启发式：轮询 jitter、连续错误退避。
fetch / 开播下播回调 / 时钟均可注入，便于离线单测。
"""
from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from config.store import ConfigStore, Room
from schedule.interval import current_minutes, room_interval

FetchFn = Callable[[str, str, str | None], Awaitable[dict]]
HookFn = Callable[[Room, dict], Awaitable[None] | None]


@dataclass
class RoomState:
    url: str
    is_live: bool = False
    recording: bool = False
    last_poll: float = 0.0
    error_count: int = 0
    interval: int = 0
    info: dict = field(default_factory=dict)
    last_error: str = ""


class Scheduler:
    def __init__(
        self,
        store: ConfigStore,
        *,
        fetch: FetchFn,
        on_live: HookFn | None = None,
        on_offline: HookFn | None = None,
        base_tick: float = 5.0,
        jitter: int = 5,
        now_fn: Callable[[], float] | None = None,
        minutes_fn: Callable[[], int] | None = None,
    ):
        self.store = store
        self.fetch = fetch
        self.on_live = on_live
        self.on_offline = on_offline
        self.base_tick = base_tick
        self.jitter = jitter
        self._now = now_fn or time.time
        self._minutes = minutes_fn or current_minutes
        self.state: dict[str, RoomState] = {}
        self.running = False

    # ---- 间隔计算 ----
    def effective_interval(self, room: Room) -> int:
        st = self.state.setdefault(room.url, RoomState(url=room.url))
        base = room_interval(
            {"poll_schedule": room.poll_schedule},
            self.store.settings.poll_schedule,
            self.store.settings.poll_interval,
            self._minutes(),
        )
        # 连续错误退避：每错一次翻倍，最多 4 次（16x），避免风控/故障时高频打接口
        if st.error_count:
            base = min(base * (2 ** min(st.error_count, 4)), 3600)
        # jitter 防多房间同拍
        if self.jitter:
            base = max(1, base + random.randint(-self.jitter, self.jitter))
        st.interval = base
        return base

    # ---- 单房间轮询 ----
    async def poll_room(self, room: Room) -> None:
        st = self.state.setdefault(room.url, RoomState(url=room.url))
        st.last_poll = self._now()
        quality = room.quality or self.store.settings.quality
        try:
            info = await self.fetch(room.url, quality, self.store.cookie())
        except Exception as e:  # noqa: BLE001 - 网络/解析异常都算一次错误
            st.error_count += 1
            st.last_error = str(e)
            return
        st.error_count = 0
        st.last_error = ""
        st.info = info
        was_live = st.is_live
        st.is_live = bool(info.get("is_live"))

        if st.is_live and not was_live:
            st.recording = True
            if self.on_live:
                await _maybe_await(self.on_live(room, info))
        elif not st.is_live and was_live:
            st.recording = False
            if self.on_offline:
                await _maybe_await(self.on_offline(room, info))

    # ---- 主循环 ----
    async def _tick(self) -> None:
        self.store.reload_if_changed()
        now = self._now()
        for room in self.store.enabled_rooms():
            st = self.state.setdefault(room.url, RoomState(url=room.url))
            interval = self.effective_interval(room)
            if now - st.last_poll >= interval:
                await self.poll_room(room)

    async def run(self) -> None:
        self.running = True
        try:
            while self.running:
                await self._tick()
                await asyncio.sleep(self.base_tick)
        finally:
            self.running = False

    def stop(self) -> None:
        self.running = False

    # ---- 状态快照（供 API）----
    def snapshot(self) -> list[dict]:
        out = []
        for room in self.store.rooms:
            st = self.state.get(room.url, RoomState(url=room.url))
            out.append({
                "id": room.id,
                "url": room.url,
                "name": room.name,
                "enabled": room.enabled,
                "is_live": st.is_live,
                "recording": st.recording,
                "interval": st.interval,
                "error_count": st.error_count,
                "last_error": st.last_error,
                "anchor_name": st.info.get("anchor_name"),
                "title": st.info.get("title"),
            })
        return out


async def _maybe_await(result):
    if asyncio.iscoroutine(result):
        await result
