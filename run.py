"""Dy-Sentry 启动入口（Windows 打包冻结用）。

本地直接运行等价于：PYTHONPATH=src uvicorn api.app:app --port 12580
打包后由 PyInstaller 冻结为本文件的可执行体。
"""
from __future__ import annotations

import os

import uvicorn

PORT = int(os.environ.get("DY_PORT", "12580"))


def main() -> None:
    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
