"""弹幕落盘录制（M5）：把实时弹幕写为 JSONL + 结束摘要。"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from capture.danmaku_source import iter_danmaku


class DanmakuRecorder:
    """订阅单个房间弹幕并追加写 JSONL；stop 时落一份类型统计摘要。"""

    def __init__(self, room_id: str, out_path: str | Path, *, anchor: str = "", title: str = ""):
        self.room_id = room_id
        self.path = Path(out_path)
        self.anchor = anchor
        self.title = title
        self.count = 0
        self.by_type: dict[str, int] = {}
        self._task: asyncio.Task | None = None
        self._file = None
        self._started_at = 0.0

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, "a", encoding="utf-8")
        self._started_at = time.time()
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            async for msg in iter_danmaku(self.room_id):
                self._file.write(json.dumps(msg, ensure_ascii=False) + "\n")
                self._file.flush()
                self.count += 1
                self.by_type[msg.get("type", "?")] = self.by_type.get(msg.get("type", "?"), 0) + 1
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 上游断连等，结束本录制
            pass

    async def stop(self) -> Path | None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        if self._file:
            self._file.close()
            self._file = None
        return self._write_summary()

    def _write_summary(self) -> Path | None:
        if not self.path.exists():
            return None
        summary = self.path.with_suffix(".summary.txt")
        duration = int(time.time() - self._started_at) if self._started_at else 0
        lines = [
            f"anchor: {self.anchor}",
            f"title: {self.title}",
            f"room_id: {self.room_id}",
            f"duration_sec: {duration}",
            f"total: {self.count}",
        ] + [f"{k}: {v}" for k, v in sorted(self.by_type.items())]
        summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return summary
