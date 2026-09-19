"""Dy-Sentry 启动入口（Windows 打包冻结用）。

本地直接运行等价于：PYTHONPATH=src uvicorn api.app:app --port 12580
打包后由 PyInstaller 冻结为本文件的可执行体。

端口优先级：命令行 --port > 环境变量 DY_PORT > 默认 12580。
桌面客户端（Tauri）通过 --port 12580 传入，保持与外壳一致。
"""
from __future__ import annotations

import argparse
import os

import uvicorn


def _parse_port() -> int:
    default = int(os.environ.get("DY_PORT", "12580"))
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--port", type=int, default=default)
    args, _ = parser.parse_known_args()
    return args.port


PORT = _parse_port()


def main() -> None:
    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
