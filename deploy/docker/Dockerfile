# Dy-Sentry 容器镜像
# 视频录制（M3）依赖系统 ffmpeg：video_recorder.py 通过子进程调用 ffmpeg，
# 故基于 Debian 系 slim 镜像并安装 ffmpeg；ca-certificates 供 WSS TLS 校验（certifi 同源）。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码（含 src/web：index.html / manage.html / vendor/mpegts.js 自托管播放器）
COPY src/ ./src/
COPY pyproject.toml ./

# 运行时数据卷：config.yaml / rooms.yaml（缺失自愈生成）+ recordings/ 录制产出。
# 工作目录设为数据卷，配置文件与录制结果均落在此，容器重建不丢。
WORKDIR /app/data

EXPOSE 12580

# uvicorn 以模块路径 api.app:app 启动；PYTHONPATH 指向 /app/src 才能解析
# api / core / config / schedule / capture 等包。DY_COOKIE 可选（提升稳定性，不写文件）。
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:12580/').status==200 else 1)"

CMD ["sh", "-c", "PYTHONPATH=/app/src DY_COOKIE=\"${DY_COOKIE}\" uvicorn api.app:app --host 0.0.0.0 --port 12580"]
