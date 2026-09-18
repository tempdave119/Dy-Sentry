# Dy-Sentry

> 针对 Dy 平台的直播间**监控 + 自动录制**工具：开播自动录视频与弹幕，停播优雅转封装，配套浏览器预览与管理后台。

Dy-Sentry 是一套个人向的录制 / 监控工具，解决两个核心痛点：

- **看流**：无需签名的房间信息接口 + 后端 FLV 代理 + 自托管 `mpegts.js`，浏览器直接实播。
- **分时段轮询**：按房间 / 时间窗配置不同的监控间隔，避免无谓频繁轮询。
- **自动录制闭环**：监控检测到开播 → 自动录视频（ffmpeg）+ 弹幕（WebSocket）→ 停播优雅转封装为 MP4 并汇总弹幕。

---

## 功能特性

- 📡 **开播监控**：基于房间信息接口轮询，支持分时段 / 按房间差异化间隔，带抖动与错误退避。
- 🎥 **视频录制**：ffmpeg 拉流录制，h265 自动回退 TS、分片、停播转封装 MP4（源 FLV 清理）。
- 💬 **弹幕录制**：WebSocket（WSS + gzip + Protobuf）实时解码，落盘 JSONL + 汇总 `summary.txt`。
- 🖥️ **浏览器预览**：自托管 `mpegts.js`，`/api/preview` 后端代理 FLV，无第三方 CDN 依赖。
- ⚙️ **管理后台**：`/manage` 可视化管理全局设置、房间增删改、逐房间开关（录制 / 弹幕 / 清晰度 / 调度）。
- 🔐 **纯 Python 签名**：`a_bogus` 与弹幕 `X-Bogus` 均为纯 Python 实现，**不依赖 V8 / Node.js / py-mini-racer**。
- 📦 **三种部署形态**：Docker 容器（`docker compose`）、Windows **桌面客户端**（Tauri 外壳 + 内置后端，双击即用、无需访问 localhost），或 Windows 服务安装包（Inno Setup，CI 自动构建）。

---

## 相关文档

- [架构设计 `docs/architecture.md`](./docs/architecture.md)：模块划分、核心数据流、纯 Python 签名方案与关键技术决策。
- [容器化 `DOCKER.md`](./deploy/docker/DOCKER.md)：Docker / Compose 部署与数据持久化。

## 快速开始

服务默认端口 **`12580`**。四种运行方式任选其一。

### 方式 A：Docker（推荐常驻 / 服务器）

详见 [`DOCKER.md`](./deploy/docker/DOCKER.md)。

```bash
# 基础启动
docker compose -f deploy/docker/docker-compose.yaml up -d --build

# 注入 Cookie（可选，提升拉流 / 弹幕稳定性，仅经环境变量进进程，不落盘）
DY_COOKIE="<你的cookie>" docker compose -f deploy/docker/docker-compose.yaml up -d --build
```

启动后访问：

- 预览页 <http://localhost:12580/>
- 管理页 <http://localhost:12580/manage>

### 方式 B：桌面客户端（Tauri，推荐）🖥️

双击安装得到的是**原生桌面应用**：启动即打开原生窗口（默认进入「管理 / 监控」页），内置 Python 后端作为 sidecar 在后台运行，**用户无需手动访问 localhost 地址**。直播预览 / 弹幕只是窗口内的一个次级入口（「预览」标签）——**监控与录制才是核心**。

> 桌面客户端由 CI 自动构建：推送 `v*` tag 触发 `.github/workflows/build-desktop.yml`，在 `windows-latest` 上完成 PyInstaller（后端 sidecar）+ Tauri（外壳）打包，产出 NSIS 安装包 `Dy-Sentry-x.y.z-x64-setup.exe`。详见下方「构建」。

### 方式 C：Windows 服务安装包（Inno Setup）

在 GitHub **Actions 产物**下载 `Dy-Sentry-vX.Y.Z-Setup.exe`，一路下一步安装（默认装到 `%LOCALAPPDATA%\Dy-Sentry`，无需管理员权限）。

安装完成后：

- 桌面 / 开始菜单「启动 Dy-Sentry」快捷方式会启动服务并自动打开预览页；
- 或在安装目录双击 `launcher.bat`。

> 该安装包由旧版 CI（`.github/workflows/build-windows.yml`）构建，偏向「服务 + 浏览器访问 localhost」形态；新项目推荐用方式 B 桌面客户端。

### 方式 D：源码直接运行

```bash
python -m pip install -r requirements.txt
python run.py                # 等价于 PYTHONPATH=src uvicorn api.app:app --port 12580
# 可选自定义端口：DY_PORT=8080 python run.py
```

---

## 配置

首次启动会在工作目录（Docker 为挂载的 `./data`，Windows 为安装目录）**自愈生成**配置文件，之后可在管理页 `/manage` 修改并落盘：

- `config.yaml`：全局设置（轮询间隔、调度等）。
- `rooms.yaml`：监控房间列表与逐房间开关。

环境变量：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `DY_PORT` | 服务端口 | `12580` |
| `DY_COOKIE` | 可选，提升拉流 / 弹幕稳定性的登录 Cookie，仅注入进程 | 空 |
| `DY_FFMPEG` | 可选，显式指定 ffmpeg 可执行路径（打包态自动查找同级目录） | 系统 PATH |

录制产物落在工作目录的 `recordings/`：视频 `*.mp4` + 弹幕 `*.jsonl` + `*.summary.txt`。

---

## 构建（从源码出安装包）

> 本机为 macOS 时 **PyInstaller / Tauri 均不支持跨平台编译**，请在 Windows 环境构建（GitHub Actions 已自动化）。

### 1) 桌面客户端（Tauri，推荐）

推送版本 tag 触发 `.github/workflows/build-desktop.yml`（运行于 `windows-latest`）：

```bash
git tag v0.1.0 && git push origin v0.1.0
```

工作流完成：装 Python 依赖 → 下载 ffmpeg → PyInstaller 冻结后端为 sidecar → `cargo tauri build` 打包外壳 + NSIS 安装包，产物 `Dy-Sentry-x.y.z-x64-setup.exe` 作为 artifact 上传（版本号自动从 tag 注入）。

关键文件：`desktop/`（Tauri 外壳：`src-tauri/` Rust 代码、`tauri.conf.json`、`frontend/` 启动屏）、`deploy/windows/dy-sentry.spec`（后端 PyInstaller 配置）。

### 2) Windows 服务安装包（Inno Setup，旧形态）

同推 `v*` tag 触发 `.github/workflows/build-windows.yml`：PyInstaller 冻结 + Inno Setup 打包，产物 `Dy-Sentry-vX.Y.Z-Setup.exe`。偏向「服务 + 浏览器访问 localhost」形态。

### 本地 Windows 一键构建

在本机 Windows 上可构建旧形态安装包：

```bat
build.bat
```

脚本会自动下载 ffmpeg 并产出 `dist\dy-sentry\` 与 `installer_output\Dy-Sentry-*-Setup.exe`。桌面客户端（Tauri）的本地构建需 Rust 工具链：在 `desktop/src-tauri` 执行 `cargo tauri build`（需先把 PyInstaller 产物重命名为 `desktop/binaries/dy-sentry-x86_64-pc-windows-msvc.exe`）。

---

## 开发 / 测试

```bash
python -m pip install -r requirements.txt
python -m pytest -q        # 累计 49/49 单测
```

技术栈：FastAPI + uvicorn（Web / 流代理 / 弹幕推送）、httpx（异步 HTTP）、websockets + betterproto（弹幕）、certifi（WSS TLS）、loguru（日志）、pyyaml（配置）；ffmpeg 作为子进程负责录制与转封装。

---

## 项目状态

- 里程碑 **M1–M7** 全部完成：监控调度、视频录制、弹幕、Web UI 整合与录制闭环、Docker 容器化、Windows 安装包（PyInstaller + Inno Setup）。
- **M8 桌面客户端（Tauri）已配置**：Rust 外壳把 Python 后端作 sidecar 启动、webview 加载管理页、带启动屏 / 托盘 / 单实例 / 优雅退出；CI 工作流 `build-desktop.yml` 已就绪，**待 CI 首次构建验证产出 NSIS 安装包**。
- 核心闭环已真实验收（开播自动录视频 + 弹幕，停播优雅转封装 MP4 + 弹幕汇总）；累计单测 **49/49**。

---

## 免责声明

本项目为**个人学习 / 自用**工具。使用者需自行遵守所在平台的服务条款与相关法规，对所录制内容的用途与授权负责。作者不对任何滥用或违规使用承担责任。
