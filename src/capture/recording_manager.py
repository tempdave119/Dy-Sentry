"""录制管理器（M5）：把调度器的开播/下播事件接到视频+弹幕录制。

on_live → 起 VideoRecorder（含 refresh 重拉流地址）+ DanmakuRecorder；
on_offline → 优雅停止两者。输出按 主播名/时间戳 组织在 settings.output_dir 下。
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from capture.danmaku_recorder import DanmakuRecorder
from capture.video_recorder import VideoRecorder, choose_container
from config.store import ConfigStore, Room
from core import fetcher


def _safe(name: str) -> str:
    return "".join(c for c in name if c not in '/\\:*?"<>|') or "unknown"


class RecordingManager:
    def __init__(self, store: ConfigStore):
        self.store = store
        self._video: dict[str, tuple[asyncio.Task, VideoRecorder]] = {}
        self._danmu: dict[str, DanmakuRecorder] = {}

    def _out_dir(self, anchor: str) -> Path:
        base = Path(self.store.settings.output_dir) / _safe(anchor)
        base.mkdir(parents=True, exist_ok=True)
        return base

    async def on_live(self, room: Room, info: dict) -> None:
        if room.url in self._video or room.url in self._danmu:
            return  # 已在录制
        anchor = info.get("anchor_name") or room.name or room.id
        out_dir = self._out_dir(str(anchor))
        ts = time.strftime("%y%m%d%H%M%S")
        vs = self.store.settings.video
        ds = self.store.settings.danmaku

        if room.record_video and vs.get("enabled", True) and info.get("flv_url"):
            flv = info["flv_url"]

            async def refresh() -> str | None:
                fresh = await fetcher.check_live_status(
                    room.url, quality=room.quality or self.store.settings.quality,
                    cookie=self.store.cookie(),
                )
                return fresh.get("flv_url")

            rec = VideoRecorder(
                flv,
                str(out_dir / f"{ts}.{choose_container(flv)}"),
                container=choose_container(flv),
                remux_mp4=vs.get("remux_mp4", True),
                segment_seconds=None,
                referer=fetcher.DEFAULT_REFERER,
                cookie=self.store.cookie(),
                refresh=refresh,
            )
            self._video[room.url] = (asyncio.create_task(rec.start()), rec)

        if room.record_danmaku and ds.get("enabled", True) and info.get("room_id"):
            dr = DanmakuRecorder(
                room_id=str(info["room_id"]),
                out_path=out_dir / f"{ts}_danmu.jsonl",
                anchor=str(anchor),
                title=str(info.get("title") or ""),
            )
            await dr.start()
            self._danmu[room.url] = dr

    async def _stop_video(self, entry: tuple[asyncio.Task, VideoRecorder]) -> None:
        task, rec = entry
        await rec.stop()
        # 等 start() 跑完转封装；超时才强制取消
        try:
            await asyncio.wait_for(task, timeout=60)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            task.cancel()

    async def on_offline(self, room: Room, info: dict) -> None:
        vid = self._video.pop(room.url, None)
        if vid:
            await self._stop_video(vid)
        dr = self._danmu.pop(room.url, None)
        if dr:
            await dr.stop()

    async def stop_all(self) -> None:
        for url in list(self._video):
            await self._stop_video(self._video.pop(url))
        for url in list(self._danmu):
            dr = self._danmu.pop(url)
            await dr.stop()

    def active(self) -> dict:
        return {
            "video": list(self._video),
            "danmaku": list(self._danmu),
        }
