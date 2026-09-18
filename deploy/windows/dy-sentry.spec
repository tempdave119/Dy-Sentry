# -*- mode: python ; coding: utf-8 -*-
"""
Dy-Sentry PyInstaller 打包配置（Windows）
用法: pyinstaller dy-sentry.spec --clean --noconfirm

与 Dy-Stream1 的区别：Dy-Sentry 的签名（a_bogus / X-Bogus）已全部是纯 Python，
不再需要 V8 / py-mini-racer / sign.js，打包更干净。

打入内容:
- src/ 全部 Python 包（api/core/config/schedule/capture）
- src/web/ 静态资源（index.html / manage.html / vendor/mpegts.js）-> 运行时 WEB_DIR
- ffmpeg 二进制（视频录制，video_recorder._ffmpeg_bin 会从 exe 同级目录解析）
"""
from __future__ import annotations

import os
import shutil
import sys

block_cipher = None

# spec 现位于 deploy/windows/，回溯两级定位仓库根（src/、run.py、bin/ 均在此）
PROJECT_DIR = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
SRC = os.path.join(PROJECT_DIR, "src")

# ---- 查找 ffmpeg 二进制（Windows 为 ffmpeg.exe）----
ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
_ffmpeg_bin = None
for _cand in (os.environ.get("FFMPEG_BIN", ""), os.path.join(PROJECT_DIR, "bin", ffmpeg_name)):
    if _cand and os.path.isfile(_cand):
        _ffmpeg_bin = _cand
        break
if _ffmpeg_bin is None:
    _sys_ffmpeg = shutil.which(ffmpeg_name)
    if _sys_ffmpeg:
        _ffmpeg_bin = _sys_ffmpeg

datas: list[tuple[str, str]] = []
if _ffmpeg_bin:
    datas.append((_ffmpeg_bin, "."))

# ---- 收集 src/web 静态资源，保持 web/ 相对结构（运行时 WEB_DIR = <dist>/web）----
_web_src = os.path.join(SRC, "web")
for _root, _dirs, _files in os.walk(_web_src):
    for _f in _files:
        _full = os.path.join(_root, _f)
        _rel = os.path.relpath(_full, SRC)  # e.g. web/vendor/mpegts.js
        datas.append((_full, os.path.dirname(_rel)))

a = Analysis(
    [os.path.join(PROJECT_DIR, "run.py")],
    pathex=[SRC],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # 本地包（含子模块，确保 PyInstaller 收集）
        "api", "api.app", "api.routes_danmaku", "api.routes_rooms",
        "api.routes_settings", "api.routes_status", "api.stream_proxy",
        "core", "core.ab_sign", "core.fetcher", "core.ws_signer",
        "core.proto", "core.proto.douyin_pb",
        "config", "config.store",
        "schedule", "schedule.interval", "schedule.scheduler",
        "capture", "capture.danmaku_source", "capture.danmaku_recorder",
        "capture.video_recorder", "capture.recording_manager",
        # 第三方依赖（纯 Python，显式列出以防漏收）
        "fastapi", "uvicorn", "starlette", "websockets", "betterproto",
        "httpx", "certifi", "yaml", "loguru",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dy-sentry",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 服务器：保留控制台看日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="dy-sentry",
)
