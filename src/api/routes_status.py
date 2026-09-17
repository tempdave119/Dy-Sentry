"""监控状态 API：快照 + WebSocket 实时推送。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, WebSocket

router = APIRouter(prefix="/api/monitor", tags=["monitor"])

WS_PUSH_INTERVAL = 2.0


@router.get("/status")
async def status(request: Request):
    scheduler = request.app.state.scheduler
    return scheduler.snapshot()


@router.websocket("/ws")
async def ws_status(websocket: WebSocket):
    await websocket.accept()
    scheduler = websocket.app.state.scheduler
    try:
        while True:
            await websocket.send_json(scheduler.snapshot())
            await asyncio.sleep(WS_PUSH_INTERVAL)
    except Exception:  # noqa: BLE001 - 客户端断开等
        pass
