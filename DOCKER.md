# Dy-Sentry 容器化（M6）

> 总览与快速开始见根目录 [`README.md`](./README.md)。

M1–M5 已完成并真实验收，M6 提供 Docker 容器化，便于一键部署与升级。
镜像基于 `python:3.12-slim`，并安装系统 `ffmpeg`（视频录制运行时依赖）。

## 文件

- `Dockerfile`：构建镜像，含 ffmpeg、依赖安装、自托管前端与 `/app/data` 数据卷。
- `docker-compose.yaml`：单服务编排，端口 `12580`、环境变量 `DY_COOKIE`、挂载 `./data:/app/data`。
- `.dockerignore`：排除 `archive/`、`_agent/`、`tests/`、`.venv/`、运行时配置与录制产物。

## 构建与启动

```bash
# 基础启动
docker compose up -d --build

# 注入 Cookie（可选，不写文件；提升拉流/弹幕稳定性）
DY_COOKIE="<你的cookie>" docker compose up -d --build
```

启动后访问：

- 预览页 `http://localhost:12580/`
- 管理页 `http://localhost:12580/manage`

## 数据持久化

`./data` 挂载到容器内 `/app/data`：

- `config.yaml` / `rooms.yaml`：首次运行自愈生成，之后由管理页修改并落盘。
- `recordings/`：录制产出（视频 MP4 + 弹幕 JSONL + 汇总）。

升级镜像（`docker compose up -d --build`）不会删除 `./data`，配置与历史录制保留。

## 说明

- 端口默认 `12580`，与本地直接运行一致（`uvicorn api.app:app --port 12580`）。
- Cookie 仅经环境变量 `DY_COOKIE` 注入进程，不写入镜像或挂载卷（红线）。
- 本镜像仅本地构建与运行；如需分发请自行推送到私有仓库（不在本任务范围）。
