"""房间 CRUD API。store 与 scheduler 通过 app.state 注入。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from config.store import room_to_dict

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


class RoomIn(BaseModel):
    url: str
    name: str = ""
    poll_schedule: str = ""
    quality: str = ""
    record_video: bool = True
    record_danmaku: bool = True
    enabled: bool = True


class RoomPatch(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    poll_schedule: str | None = None
    quality: str | None = None
    record_video: bool | None = None
    record_danmaku: bool | None = None


@router.get("")
async def list_rooms(request: Request):
    store = request.app.state.store
    return [room_to_dict(r) for r in store.rooms]


@router.post("", status_code=201)
async def add_room(body: RoomIn, request: Request):
    store = request.app.state.store
    try:
        room = store.add_room(
            body.url,
            name=body.name,
            poll_schedule=body.poll_schedule,
            quality=body.quality,
            record_video=body.record_video,
            record_danmaku=body.record_danmaku,
            enabled=body.enabled,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return room_to_dict(room)


@router.delete("/{room_id}")
async def remove_room(room_id: str, request: Request):
    store = request.app.state.store
    if not store.remove_room(room_id):
        raise HTTPException(status_code=404, detail="room not found")
    return {"removed": room_id}


@router.patch("/{room_id}")
async def patch_room(room_id: str, body: RoomPatch, request: Request):
    store = request.app.state.store
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not store.update_room(room_id, **fields):
        raise HTTPException(status_code=404, detail="room not found")
    return room_to_dict(store.get_room(room_id))
