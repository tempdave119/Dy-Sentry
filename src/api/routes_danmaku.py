"""弹幕实时推送 API：把 Dy 弹幕 WS 桥接给前端。"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from capture.danmaku_source import iter_danmaku

router = APIRouter(prefix="/api/danmaku", tags=["danmaku"])


@router.websocket("/ws")
async def danmaku_ws(websocket: WebSocket, room_id: str):
    """订阅指定房间的实时弹幕；服务端从 Dy 弹幕 WS 拉取并转发。"""
    await websocket.accept()
    gen = iter_danmaku(room_id)
    try:
        async for msg in gen:
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 - 上游断连等，结束本订阅
        pass
    finally:
        await gen.aclose()
