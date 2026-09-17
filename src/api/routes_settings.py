"""全局设置 API：读取/修改 config.yaml 的运行参数。"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request
from pydantic import BaseModel

from config.store import Settings

router = APIRouter(prefix="/api/settings", tags=["settings"])

_EDITABLE = set(Settings.__dataclass_fields__)


class SettingsPatch(BaseModel):
    output_dir: str | None = None
    poll_interval: int | None = None
    poll_schedule: str | None = None
    quality: str | None = None
    log_level: str | None = None
    video: dict | None = None
    danmaku: dict | None = None


@router.get("")
async def get_settings(request: Request):
    return asdict(request.app.state.store.settings)


@router.patch("")
async def patch_settings(body: SettingsPatch, request: Request):
    store = request.app.state.store
    s = store.settings
    for key, val in body.model_dump(exclude_none=True).items():
        if key in _EDITABLE:
            if key in ("video", "danmaku"):
                getattr(s, key).update(val)
            else:
                setattr(s, key, val)
    store.save_settings()
    return asdict(s)
