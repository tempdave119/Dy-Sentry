# Dy-Sentry 项目规划与报告

> 状态：已落地（M1–M7 完成，2026-09-19）。配套设计文档见 `docs/architecture.md`（已校正至纯 Python 实现）。
> 命名约束：全文用「Dy」指代目标平台；存档用缩写 `DANMU`/`STREAM1`/`DLR`/`SREC`，不拼平台全名。

---

## A. 调研报告（结论先行）

### A1. 需求本质
用户在 `SREC`（在用的多平台录制器）上有两个无法自主解决的痛点，外加一个战略诉求：

| 编号 | 痛点/诉求 | 根因 | 现成解法 |
|---|---|---|---|
| 痛点1 | 拉流失败 + 无法直接看流 | Dy 更新签名算法，修复点在 `SREC` 的 Rust 引擎内，用户改不动、只能等上游 | `DLR` 的纯 Python `a_bogus` + 后端代理预览 |
| 痛点2 | 监控轮询是全局固定间隔 | `SREC`/`DLR` 都无分房间分时段轮询 | `DANMU` 已实现 `resolve_schedule_interval` |
| 战略 | 多平台体量大、迭代受制上游 | `SREC` 支持 12+ 平台，对 Dy-only 用户是负担 | 精简自研 Dy-only |

### A2. 四存档调研结论

| 存档 | 类型 | 关键可复用资产 | 关键缺陷 |
|---|---|---|---|
| `DANMU` | 自研·弹幕 | **分房间分时段轮询**（痛点2 唯一现成实现）、protobuf 弹幕管线、V8 弹幕签名、JSONL/HTML/摘要输出 | 无视频、无 Web、弹幕无重连、源码模式路径损坏 |
| `STREAM1` | 自研·半成品 | 模块化拆分、ffmpeg 视频录制+分片+转封装 | URL 不刷新（无限重启）、清晰度死代码、全局固定间隔、无 Web |
| `DLR` | 第三方·血缘源头 | **纯 Python a_bogus 签名**、Dy 拉流三级回退、ORIGIN 原画前置、清晰度探测降级、ffmpeg 参数+h265→TS 回退、jitter/退避启发式、自愈+备份配置 | 全局固定间隔、无弹幕、无 HTTP 服务（index.html 静态不能设头） |
| `SREC` | 第三方·在用 | 架构对标：`/player` 预览、`filters` 调度、REST API+OpenAPI+JWT+health、Web UI；**纯 Python `signature.rs` 弹幕 X-Bogus** | 体量大、Rust、签名改不动 |

### A3. 核心判断
- **痛点2 几乎零风险**：`DANMU` 已有成熟实现，直接移植。
- **痛点1 可自维护**：HTTP 签名走纯 Python a_bogus（改算法只动一个文件），预览走后端代理注入头——两者都绕开了 `SREC` 改不动的 Rust 引擎。弹幕签名同理移植 `SREC` 的纯 Python `signature.rs`，同样无需 JS 引擎。
- **新建轻量 Dy-only 工具是正确路线**：复用四存档的高价值资产，重写不适配 Web/异步的监控-配置-入口层。

---

## B. §12 开放问题决策（我来拍板，附理由）

| # | 问题 | 决策 | 理由 |
|---|---|---|---|
| 1 | 配置格式 | **YAML** | 房间配置含嵌套（per-room poll_schedule、视频/弹幕子项），YAML 对嵌套+注释更友好；TOML 的 array-of-tables 写多房间更啰嗦。用 `PyYAML`。 |
| 2 | 前端形态 | **首期原生静态页 + mpegts.js/flv.js**，不引入构建链 | 符合「精简」诉求、单人维护、首期 UI 仅房间管理+调度+预览+状态，复杂度低。UI 明显变复杂时再评估轻框架。 |
| 3 | Web 鉴权 | **默认本地无鉴权；提供可选 token 开关** | 对标 `SREC` 的 JWT 偏重；首期本地访问为主，暴露到网络时启用简单 token 即可。 |
| 4 | Docker | **已完成（M6）：Dockerfile + compose** | 三参考项目均有、部署方便；先本地跑通，M6 容器化已落地。另提供 Windows 安装包（M7，PyInstaller + Inno Setup，GitHub Actions `windows-latest` 原生构建）。 |
| 5 | X-Bogus 纯 Python | **已实现纯 Python，V8/sign.js 弃用** | 移植自 SREC `signature.rs`（`core/ws_signer.py`，RC4 + 自定义 base64），无需 JS 引擎；`py-mini-racer`/`PyExecJS`/`Node` 全部弃用，跨平台打包零原生依赖。 |

---

## C. 技术栈（锁定）

- 语言：Python 3.11+
- 后端：FastAPI + uvicorn（单异步事件循环）
- 前端：原生静态页 + mpegts.js/flv.js
- 拉流录制：ffmpeg（外部）
- 弹幕：websockets + betterproto
- 签名：HTTP=`a_bogus`（纯 Python）；弹幕 WS=X-Bogus（纯 Python，移植自 SREC `signature.rs`，无需 V8/sign.js）
- 配置：YAML（PyYAML）
- 日志：loguru
- 依赖：`httpx certifi websockets betterproto fastapi uvicorn loguru pyyaml` + 外部 `ffmpeg`；`PyExecJS`/`Node`/`py-mini-racer`(V8) 显式弃用（签名纯 Python 化后无原生依赖）

---

## D. WBS 工作分解

### M1 — 拉流 + 签名 + 预览（解决痛点1）
- 1.1 搭项目骨架：`src/` 分层目录、`requirements.txt`、配置加载骨架（YAML schema + store）
- 1.2 移植 `core/ab_sign.py`（a_bogus，纯 Python）+ 单测（给定 query→稳定签名）
- 1.3 移植重写 `core/fetcher.py`：room_id 解析、enter API、开播状态、拉流地址；三级回退（web→app→HTML）；ORIGIN 原画前置；清晰度 HEAD 探测降级
- 1.4 `api/stream_proxy.py`：后端代理 FLV/HLS，注入 Referer/Cookie
- 1.5 最小前端预览页：输入/选择房间 → mpegts/flv.js 播放
- **验收**：给定真实房间，能稳定取到开播状态与流地址，并在浏览器预览播放
- **依赖**：无（起点）

### M2 — 分房间分时段监控调度（解决痛点2）
- 2.1 移植 `schedule/interval.py`：`resolve_schedule_interval`（HH:MM-HH:MM=秒，跨午夜，首匹配优先）+ 单测
- 2.2 `schedule/scheduler.py`：单异步循环 + 房间注册表 + per-room `last_poll`；优先级 房间>全局>默认
- 2.3 健壮性：jitter、连续错误退避、录制后快重查（借鉴 `DLR`）
- 2.4 配置热重载：监听 `rooms.yaml` mtime，增删改即时生效
- 2.5 `api/routes_rooms.py` + `routes_status.py`：房间 CRUD、启停、状态 WS 推送
- **验收**：不同时段轮询间隔按配置生效；改 `rooms.yaml` 热生效；状态可在前端观测
- **依赖**：M1

### M3 — 视频录制
- 3.1 `capture/video_recorder.py`：ffmpeg 拉流（移植 `DLR` 参数）+ `-c copy` 转封装 MP4
- 3.2 h265→TS/HLS 容器自动回退
- 3.3 清晰度选择真正接线（修 `STREAM1` 死代码）
- 3.4 录制中周期重取流地址（修 `STREAM1` URL 过期无限重启）
- 3.5 分片（按大小/时长）+ 优雅停止（POSIX SIGINT / Windows 写 `q`）
- 3.6 接入 scheduler：开播自动启停
- **验收**：开播自动录制，文件完整可播，清晰度可选，长录不过期、可分片
- **依赖**：M2

### M4 — 弹幕录制
- 4.1 `core/ws_signer.py`：X-Bogus 纯 Python 实现（RC4 + 自定义 base64，移植自 SREC `signature.rs`），无需 V8/sign.js
- 4.2 `capture/danmaku_recorder.py`：WS 连接 + protobuf 解码（移植 `DANMU`/`STREAM1` proto）→ JSONL + 摘要
- 4.3 **新增断线重连**：心跳 + 指数退避 + 存活探测（补两存档缺陷）
- 4.4 动态生成设备 id/时间戳，去硬编码
- 4.5 接入 scheduler：与视频并行启停
- **验收**：弹幕完整落 JSONL，断网后自动恢复，9 类消息分类正确
- **依赖**：M2（与 M3 可并行）

### M5 — Web UI 整合
- 5.1 房间管理页（增删改、启用、清晰度、录制开关）
- 5.2 调度配置页（分时段轮询间隔可视化编辑）
- 5.3 实时状态面板（监控/录制中、WS 推送）
- 5.4 预览播放器整合（复用 M1.5）
- 5.5 可选 token 鉴权开关
- **验收**：全流程可在 UI 操作与观测
- **依赖**：M1–M4

### M6 — 容器化（已完成）
- 6.1 Dockerfile + docker-compose（对标 `DLR`/`SREC`/`STREAM1`）：已落地，`docker compose -f deploy/docker/docker-compose.yaml up -d --build` 一键部署
- 6.2 ffmpeg 随镜像安装（apt），运行入口 `uvicorn api.app:app --port 12580`
- **依赖**：M5

### M7 — Windows 安装包（已完成）
- 7.1 `run.py` 冻结入口 + `dy-sentry.spec`（PyInstaller onedir），打包 `src/web/` 与 `ffmpeg.exe`
- 7.2 `installer.iss`（Inno Setup）→ `Dy-Sentry Setup.exe`，装到 `%LOCALAPPDATA%\Dy-Sentry`
- 7.3 `.github/workflows/build-windows.yml`：`windows-latest` 原生构建，推 `v*` tag 出带版本号安装包（仅 artifact，不挂 Release）
- 7.4 `src/capture/video_recorder.py` 增加 `_ffmpeg_bin()`/`_ffmpeg_available()`，优先从 `_MEIPASS`/exe 同级解析 ffmpeg，向后兼容 PATH
- **依赖**：M6

### M8 — 桌面客户端（Tauri，配置就绪 / 待 CI 验证）
- 8.1 需求：用户要**独立客户端**（双击打开原生窗口、不访问 localhost），而非「本地起服务再开浏览器」。参考存档 `rust-srec` 的 Tauri 架构。
- 8.2 `desktop/src-tauri/`：Rust 外壳（`Cargo.toml` / `build.rs` / `tauri.conf.json` / `capabilities/default.json` / `src/main.rs` / `src/lib.rs`），`externalBin` 指向 `desktop/binaries/dy-sentry`，`bundle.targets=["nsis"]`。
- 8.3 运行模型：启动屏 → 以 app data 目录为 `cwd` 拉起 PyInstaller 冻结的 Python 后端作 sidecar → 轮询 `/health` 就绪后打开主窗口指向 `/manage`（监控/录制核心）→ 托盘 / 单实例 / 关闭最小化到托盘 / 退出杀掉 sidecar 进程树（含 ffmpeg）。
- 8.4 `src/api/app.py` 新增 `GET /health`（启动屏探测后端就绪）。
- 8.5 `desktop/frontend/index.html` 启动屏；`desktop/binaries/` 放 CI 期生成的 `dy-sentry-x86_64-pc-windows-msvc.exe`（gitignore）。
- 8.6 `.github/workflows/build-desktop.yml`：`windows-latest` 先 PyInstaller 出 sidecar → 重命名放入 `desktop/binaries/` → `cargo tauri build` 出 NSIS 安装包（版本随 tag 注入）。
- 8.7 前端复用现有 `src/web`，webview 直接加载后端页面（同源）；默认进管理页，预览为次级入口——**监控+录制是核心，直播预览只是场景之一**。
- **依赖**：M7
- **边界**：本机 macOS 无法本地验证 Tauri 构建（无 Rust/Windows），以 CI 为准；产物未签名，SmartScreen 可能告警。

---

## E. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| Dy 再次更新签名算法 | 拉流或弹幕中断 | 签名集中在 `core/`，HTTP 改 `ab_sign.py`、WS 改 `ws_signer.py`；文档化修复点；M1/M4 各做签名单测便于快速定位 |
| （已消除）弹幕签名原生依赖 | 历史上 V8/PyMiniRacer 平台兼容风险 | 已实现纯 Python X-Bogus，移除全部 JS 引擎依赖，跨平台打包无障碍 |
| 流地址 header-gated | 预览/录制失败 | 后端代理统一注入 Referer/Cookie，不让前端直链 |
| h265 流容器不兼容 | 录制文件损坏 | 移植 `DLR` 的 h265→TS 回退 |
| 长录 URL 过期 | 无限重启/空文件 | M3.4 周期重取地址 |
| 合规与平台 ToS | 账号/法律风险 | 仅录制用户有权访问的公开直播；Cookie/密钥不进仓库、不进日志（全局红线）；本地自用为先 |

---

## F. 交付物清单
- `docs/architecture.md`（已落档，已落地）
- `docs/plan.md`（本文档）
- M1–M7 各阶段代码于 `src/`，验证记录写入 `_agent/ROADMAP.md` 与 `_agent/contents_p.md`

## G. 状态与后续
M1–M7 已全部完成并通过验收（单测 49/49）。后续可选项：
- 代码签名：面向外部分发消除 Windows SmartScreen 警告，需 EV 证书 + CI secrets（预留接口即可）。
- macOS/Linux 打包 workflow：复用 PyInstaller spec，补 GitHub Actions matrix。
- 更多平台特性：按需从 `SREC` 对标迁移。
