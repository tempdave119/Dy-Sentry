"""FastAPI 入口：预览 + 房间管理 + 监控状态。

运行（项目根，已建 .venv）：
    PYTHONPATH=src DY_COOKIE="<可选>" .venv/bin/uvicorn api.app:app --port 12580

Cookie 从环境变量 DY_COOKIE 注入，不写入任何文件（红线）。
build_app 为工厂，便于测试注入临时配置路径；模块级 app 供 uvicorn 使用。
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from api.routes_danmaku import router as danmaku_router
from api.routes_rooms import router as rooms_router
from api.routes_settings import router as settings_router
from api.routes_status import router as status_router
from api.stream_proxy import DEFAULT_UA, iter_flv
from capture.recording_manager import RecordingManager
from config.store import ConfigStore
from core import fetcher
from schedule.scheduler import Scheduler

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
REFERER = fetcher.DEFAULT_REFERER


def _cookie() -> str | None:
    return os.environ.get("DY_COOKIE") or None


def build_app(config_path: str = "config.yaml", rooms_path: str = "rooms.yaml") -> FastAPI:
    store = ConfigStore(config_path=config_path, rooms_path=rooms_path)

    async def _fetch(url: str, quality: str, cookie: str | None) -> dict:
        return await fetcher.check_live_status(url, quality=quality, cookie=cookie)

    manager = RecordingManager(store)
    scheduler = Scheduler(store, fetch=_fetch, on_live=manager.on_live, on_offline=manager.on_offline)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(scheduler.run())
        try:
            yield
        finally:
            scheduler.stop()
            task.cancel()
            await manager.stop_all()

    app = FastAPI(title="Dy-Sentry", version="0.3.0", lifespan=lifespan)
    app.state.store = store
    app.state.scheduler = scheduler
    app.state.manager = manager
    app.include_router(rooms_router)
    app.include_router(status_router)
    app.include_router(danmaku_router)
    app.include_router(settings_router)

    app.mount("/vendor", StaticFiles(directory=WEB_DIR / "vendor"), name="vendor")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/manage")
    async def manage() -> FileResponse:
        return FileResponse(WEB_DIR / "manage.html")

    @app.get("/health")
    async def health() -> JSONResponse:
        # 供桌面客户端启动屏轮询：返回 200 即表示后端已就绪（端口监听成功）。
        return JSONResponse({"status": "ok", "version": app.version})

    @app.get("/api/status")
    async def status(
        url: str = Query(..., description="Dy 直播间 URL，如 https://live.douyin.com/<web_rid>"),
        quality: str = Query("OD"),
    ) -> JSONResponse:
        info = await fetcher.check_live_status(url, quality=quality, cookie=_cookie())
        return JSONResponse(info)

    @app.get("/api/preview", response_model=None)
    async def preview(
        url: str = Query(...),
        quality: str = Query("OD"),
    ) -> StreamingResponse | JSONResponse:
        info = await fetcher.check_live_status(url, quality=quality, cookie=_cookie())
        if not info.get("is_live") or not info.get("flv_url"):
            return JSONResponse({"error": "not live or no flv url", "detail": info}, status_code=409)
        return StreamingResponse(
            iter_flv(info["flv_url"], referer=REFERER, cookie=_cookie(), user_agent=DEFAULT_UA),
            media_type="video/x-flv",
        )

    return app


app = build_app()
