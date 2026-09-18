# Dy-Sentry 架构方案

> 状态：已落地（M1–M7 完成，2026-09-19）。设计草案 v1 写于 2026-09-18，下方已按最终实现校正签名与依赖（纯 Python、零 JS 引擎）。使用方式见根目录 [`README.md`](../README.md)。
>
> 命名约束：项目所有文件统一用「Dy」指代目标平台，不出现平台全名。下文引用的只读存档以其外部仓库名存在于 `archive/`，本文一律用缩写指代，不拼写全名：
> - `DANMU` = 自研历史项目（纯弹幕录制，含分时段轮询调度）
> - `STREAM1` = 自研历史项目（视频+弹幕，半成品，模块化拆分）
> - `DLR` = 第三方对标项目（Python，多平台录制器，本项目早期血缘源头）
> - `SREC` = 第三方对标项目（Rust，用户在用的多平台录制器）

---

## 1. 目标与非目标

### 目标
做一个**仅面向 Dy 平台**的轻量直播录制与监控工具，解决用户在 `SREC` 上遇到、且无法自主跟进的两个核心痛点：

1. **痛点1 — 拉流可自维护 + 直播流可预览**：平台更新签名/算法导致拉流失败时，能自行快速修复，不依赖上游；并能在 Web UI 直接预览直播流。
2. **痛点2 — 分房间、分时段的开播状态轮询**：按房间 ID + 时间段配置不同的「开播状态轮询间隔」（如黄金时段密轮询、深夜疏轮询）。`SREC` 与 `DLR` 都只有全局固定间隔。

附带诉求：精简掉多平台负担，自主、可持续地做 Dy 专项功能迭代。

### 非目标（首期不做）
- 多平台支持（仅 Dy）。
- 录制后处理（弹幕渲染、转码、自动上传）——参考 `DanmakuRender`/`biliLive-tools`，留作后续迭代。
- 移动端原生 App。

---

## 2. 技术栈与理由

| 维度 | 选型 | 理由 |
|---|---|---|
| 语言 | **Python 3.11+** | 所有高价值可复用资产（a_bogus 签名、protobuf 弹幕解析、ffmpeg 拉流、Dy 逆向知识）均为 Python；签名是最难、最需自维护的部分，已在 Python 中成熟。 |
| 后端 | **FastAPI + uvicorn**（异步） | Web UI 与实时预览需要异步 HTTP/WS；单事件循环优于存档里的 thread-per-room。 |
| 前端 | 轻量 SPA + **mpegts.js / flv.js** 播放器 | 对标 `SREC` 的 `/player`、`DLR` 的 `index.html`；播放 FLV/HLS。 |
| 拉流录制 | **ffmpeg**（外部依赖） | 直接复制 `-c copy` 转封装，无损、不转码。 |
| 弹幕 | `websockets` + `betterproto` | WS 长连 + Protobuf 解码。 |
| 签名 | HTTP=`a_bogus`（纯 Python）；弹幕 WS=`X-Bogus`（纯 Python） | 见 §5，零 JS 引擎。 |
| 配置 | **YAML 或 TOML** | 取代存档的中文键 INI；干净 schema、可校验。 |
| 日志 | `loguru` | 轻量、分级落盘。 |

依赖清单：`httpx websockets betterproto fastapi uvicorn loguru pyyaml certifi` + 外部 `ffmpeg`（签名均为纯 Python，无 JS 引擎依赖）。
**显式弃用**：`PyExecJS` / Node.js（`DLR` 仅为非 Dy 平台才需要，Dy 路径用纯 Python a_bogus，无需 V8 之外的任何 JS 引擎）。

---

## 3. 架构分层

```
Dy-Sentry/
├─ src/
│  ├─ core/
│  │   ├─ ab_sign.py        # a_bogus 纯 Python（HTTP API 签名）— 移植自 DLR/STREAM1
│  │   ├─ ws_signer.py      # X-Bogus（弹幕 WS 签名）纯 Python，移植自 SREC signature.rs
│  │   ├─ fetcher.py        # Dy 房间信息/开播状态/拉流地址，三级回退 — 移植重写
│  │   └─ proto/            # 弹幕 .proto + betterproto 生成码 — 移植自 DANMU/STREAM1
│  ├─ capture/
│  │   ├─ video_recorder.py # ffmpeg 拉流录制（含 h265→TS 回退、分片、URL 刷新）
│  │   └─ danmaku_recorder.py# WS 弹幕录制（补断线重连）→ JSONL/HTML/摘要
│  ├─ schedule/
│  │   ├─ scheduler.py      # 单异步事件循环 + 房间注册表；分时段轮询间隔
│  │   └─ interval.py       # resolve_schedule_interval 移植 + jitter/退避启发式
│  ├─ api/
│  │   ├─ app.py            # FastAPI 入口
│  │   ├─ routes_rooms.py   # 房间 CRUD、启停
│  │   ├─ routes_status.py  # 监控/录制状态，WS 实时推送
│  │   └─ stream_proxy.py   # 直播流代理（注入 Referer/Cookie 头）— 预览关键
│  ├─ web/                  # 前端静态资源：房间管理 / 调度配置 / 实时预览播放器
│  └─ config/
│      ├─ schema.py         # 配置数据类 + 校验
│      └─ store.py          # 加载/热重载/自愈/自动备份
├─ config.yaml             # 全局配置（运行时生成，不进仓库）
├─ rooms.yaml              # 房间列表 + 分时段调度（运行时，不进仓库）
├─ requirements.txt
├─ docs/
├─ archive/                # 只读参考存档（建独立仓库时 gitignore）
└─ _agent/                 # 协作上下文（建独立仓库时 gitignore）
```

模块职责单一；`core` 无副作用、可单测；`schedule`/`capture` 为后台任务；`api` 只做编排与对外接口。

---

## 4. 数据流

### 监控 → 录制
```
scheduler(异步循环)
  └─ 每 tick：按房间「当前时段轮询间隔」判断是否到期
       └─ fetcher.check_live_status(room)   # a_bogus 签名，三级回退
            ├─ 未开播 → 记录下次轮询时间，sleep
            └─ 开播   → 启动 capture 任务：
                 ├─ video_recorder.start(stream_url, quality)   # ffmpeg 子进程
                 └─ danmaku_recorder.start(room)                # WS + protobuf
       └─ 状态变化经 api WS 推送前端
```

### 直播预览
```
前端播放器 → GET /api/preview/{room_id}
  └─ stream_proxy：fetcher 取实时 flv/m3u8 地址
       └─ 后端拉流并注入 Referer/Cookie，转发给前端
            └─ mpegts.js/flv.js 播放
```
> 关键：预览**必须经后端代理**。`DLR` 的静态 `index.html` 不能设请求头，header-gated 的流播不了；后端代理可注入头，稳定可播。

---

## 5. 签名策略（痛点1 的自维护核心）

Dy 有**两套独立签名**，分别处理，互不影响：

| 用途 | 签名 | 实现 | 平台改算法时的修复点 |
|---|---|---|---|
| HTTP API（房间信息、开播状态、拉流地址） | `a_bogus` | **纯 Python**（`ab_sign.py`，仅依赖 `math`/`time`，含 SM3+RC4+自定义 base64） | 改 `core/ab_sign.py` 的常量/字节布局表 |
| 弹幕 WebSocket | `X-Bogus`（signature 参数） | **纯 Python**（`ws_signer.py`：RC4+自定义字母表 base64，移植 SREC `signature.rs`） | 改 `core/ws_signer.py` 的常量/字母表/字节布局 |

设计要点：
- **两条签名路径均零 V8/零 JS 引擎**：可单测、可快速改；这是相比 `SREC`（拉流签名在 Rust 引擎内、改不动）与存档 `DANMU`（依赖 V8+sign.js）的核心优势。
- 弹幕 WS 升级**必须带 signature**（无签名服务器回 HTTP 200 拒绝升级），与 enter API（可无签名）不同。
- 握手头需 `Origin` + `User-Agent` + `Cookie(ttwid)`；WSS 主机证书链含自签根，TLS 用 certifi 证书包校验（不关闭校验）。
- 两套签名的「修复点」都集中在 `core/`，文档化在本节，确保「平台改算法→自己快速跟进」可落地。

> **现状实测（2026-09-18，真实房间）**：
> - 存档移植的 `a_bogus` **已被平台淘汰**——带签名的 enter API 返回空 body，**不带签名可正常返回**。fetcher 采用「无签名优先、空响应回退签名」。
> - 存档 `DANMU` 的 `sign.js`(JSVMP)/V8 同样失效；弹幕 WS 改用**纯 Python X-Bogus**（移植 SREC 当前算法）后**真实接通弹幕**（chat/enter/like/stats 均解码，含昵称）。`py-mini-racer`/`sign.js` 已移除。
> - 即 HTTP 与 WS 两条路径当前均**不依赖任何 JS 引擎**即可工作。

---

## 6. 调度器（痛点2 核心）

- **分房间 + 分时段轮询间隔**：移植 `DANMU` 的 `resolve_schedule_interval()`，解析 `"HH:MM-HH:MM=秒数,..."`，支持跨午夜、首个匹配优先。
- **优先级**：房间级 `poll_schedule` > 全局 `poll_schedule` > 全局 `poll_interval`（默认值）。
- **循环模型**：单异步事件循环 + 房间注册表（弃用 `DLR`/`DANMU` 的 thread-per-room 与动态命名）。每房间维护 `last_poll`，tick 时按当前时段间隔判断是否到期。
- **借鉴 `DLR` 的健壮性启发式**：轮询加 jitter（±随机秒）、连续错误退避（错误计数超阈值时拉长间隔）、录制刚结束不久则快速复查。
- **热重载**：监听 `rooms.yaml` mtime，房间增删改即时生效；运行中房间可在下个 tick 应用新间隔。

---

## 7. 录制

### 视频（`video_recorder.py`）
- ffmpeg `-c copy` 拉流转封装，**不转码**；参数移植 `DLR`（`-rw_timeout`、`-reconnect_*`、`-fflags +discardcorrupt`、`-avoid_negative_ts` 等）。
- **容器/编码适配**：Dy 优先 FLV；**当 codec=h265 时 FLV 装不下，自动回退 HLS/TS**（移植 `DLR` 的实战细节，`STREAM1` 缺此处理）。
- 清晰度：5 档（原画/蓝光/超清/高清/标清），ORIGIN 原画前置为 index 0；HEAD 探测失败降级到相邻档（移植 `DLR` 的 `stream.py` 选择逻辑）。
- 分片：按文件大小或时长切割。
- **必须修复 `STREAM1` 的两个 bug**：
  1. 录制中**周期性重新拉取流地址**，避免 URL 过期导致无限重启；
  2. 清晰度配置**真正传入** ffmpeg（`STREAM1` 里是死代码，配置被忽略）。
- 优雅停止：POSIX 用 SIGINT、Windows 用向 stdin 写 `q`，确保文件头完整。

### 弹幕（`danmaku_recorder.py`）
- WS 长连 + Protobuf 解码（移植 `DANMU`/`STREAM1` 的 `protobuf/` 与解析），9 类消息 → JSONL（带 interactive/ambient/system 分类）+ 可读摘要。
- **必须新增断线重连**：两个存档都是单次 `run_forever`、无重连、存活检测失效。设计心跳 + 指数退避重连 + 连接存活探测。
- 动态生成设备 id / 时间戳参数，避免存档里硬编码的 2024 陈旧值。

---

## 8. 配置 Schema（示例）

`config.yaml`（全局）：
```yaml
output_dir: ./recordings
poll_interval: 60          # 默认轮询秒数（无时段命中时）
poll_schedule: "19:00-23:00=20, 23:00-07:00=180"   # 全局分时段
quality: origin            # origin/BD/UHD/HD/SD/LD
video:
  enabled: true
  segment_size_mb: 1024
  remux_mp4: true
danmaku:
  enabled: true
  reconnect: true
cookie: ""                 # 不进仓库；走环境变量或本地配置
proxy: ""
log_level: INFO
```

`rooms.yaml`（房间列表 + 分时段调度）：
```yaml
rooms:
  - id: "123456789"        # 房间/主播标识
    url: "https://live.dy.example/123456789"
    name: "Anchor A"
    enabled: true
    poll_schedule: "20:00-22:00=15, 22:00-02:00=120"  # 房间级覆盖全局
    quality: BD
    record_video: true
    record_danmaku: true
```
> URL 为占位示例，实际域名以运行时配置为准，不写入仓库。Cookie/密钥不进代码、不进 commit、不进日志（遵循全局红线）。

配置借鉴 `DLR`：缺失键自愈写回默认值、按 md5 变更自动备份（保留 N 份）。

---

## 9. 复用 vs 重写映射

| 能力 | 来源（缩写:路径） | 处置 |
|---|---|---|
| a_bogus HTTP 签名 | `DLR:src/ab_sign.py`、`STREAM1:ab_sign.py` | 移植（纯 Python，零依赖） |
| 弹幕 WS 签名 | `DANMU:src/signer.py` + `js/sign.js` | 移植为纯 Python（`ws_signer.py`），sign.js / V8 已弃用 |
| Protobuf 弹幕解析 | `DANMU:protobuf/`、`STREAM1:protobuf/` | 移植 |
| Dy 拉流/房间信息 | `DLR:src/spider.py`(Dy 三入口)、`DLR:src/stream.py`、`DLR:src/room.py` | 移植重写（三级回退、ORIGIN 前置、清晰度探测） |
| ffmpeg 视频录制 | `DLR:main.py`(ffmpeg 参数/h265 回退)、`STREAM1:recorder.py`(分片/转封装) | 移植并修 bug（URL 刷新、清晰度接线、Windows 停止） |
| 弹幕录制管线 | `DANMU:src/danmaku.py`、`STREAM1:danmaku.py` | 移植 + 新增重连 |
| 分时段轮询调度 | `DANMU:src/config.py:resolve_schedule_interval` + `monitor.py` tick | 移植（痛点2 现成实现） |
| 轮询健壮性启发式 | `DLR:main.py`（jitter/退避/快重查/自适应并发） | 借鉴 |
| 看流播放 | `SREC:frontend/.../player`、`DLR:index.html` | 对标重做（后端代理 + mpegts/flv.js） |
| Web 架构/API | `SREC:rust-srec/src/api`（routes/openapi/jwt/health） | 对标设计（FastAPI 等价物） |
| 监控/配置/入口 | 各存档 `monitor.py`/`config.py`/`main.py` | **全新重写**（异步、注册表、干净 schema） |

---

## 10. 已知坑清单（新架构必须规避）

- 弹幕无断线重连（两存档）→ 新增重连与存活探测。
- 视频录制不刷新流地址 → URL 过期无限重启（`STREAM1`）→ 周期重取。
- 清晰度选择是死代码（`STREAM1`）→ 配置真正接线。
- h265 流 FLV 装不下（`DLR` 已处理，`STREAM1` 缺）→ 容器自动回退。
- thread-per-room + 动态命名 + 每次 fetch `asyncio.run()`（`DLR`）→ 单事件循环 + 注册表。
- WSS 参数硬编码（设备 id、2024 时间戳）→ 动态生成。
- 脆弱的 HTML room_id 正则 + 永不失效缓存（`STREAM1`）→ 加失效与回退。
- `httpx verify=False`、无测试、源码模式路径损坏（仅打包能跑，`DANMU`）→ 规范包结构 + 加测试。
- 中文键 INI + 迁移残留 → 干净 YAML/TOML schema。

---

## 11. 里程碑

| 阶段 | 交付 | 验收 |
|---|---|---|
| **M1** 拉流+签名打通 | `core/`(ab_sign/fetcher) + 最小 API，取到开播状态与 flv/m3u8 地址；后端代理预览可播 | 给定房间能稳定取流并在浏览器预览（痛点1） |
| **M2** 分时段监控调度 | `schedule/` + `config/` + `rooms.yaml`，分房间分时段轮询，热重载 | 不同时段轮询间隔按配置生效（痛点2） |
| **M3** 视频录制 | `capture/video_recorder.py`，ffmpeg 拉流+转封装+分片+h265 回退，修 URL 刷新/清晰度 | 开播自动录制，文件完整可播，清晰度可选 |
| **M4** 弹幕录制 | `capture/danmaku_recorder.py` + `core/ws_signer`，WS+protobuf+重连 | 弹幕完整落 JSONL，断线自动恢复 |
| **M5** Web UI 整合 | 房间管理 / 调度配置 / 实时状态 / 预览播放器 | 全流程可在 UI 操作与观测 |
| **M6** 容器化 | `Dockerfile` + `docker-compose.yaml` + `DOCKER.md` | `docker compose up -d --build` 可起服务并持久化数据 |
| **M7** Windows 安装包 | PyInstaller `dy-sentry.spec` + Inno Setup `installer.iss` + `build.bat` + CI | 推 `v*` tag 出 `Dy-Sentry-vX.Y.Z-Setup.exe` |
| **M8** 桌面客户端（Tauri） | Rust 外壳（`desktop/`）把 Python 后端作 sidecar 启动，webview 加载管理页，带启动屏 / 托盘 / 单实例 / 优雅退出 | 推 `v*` tag 出 NSIS 桌面安装包；双击打开原生窗口，无需访问 localhost |

每个里程碑完成并验证后才更新 `ROADMAP.md` 的「已完成」。

---

## 12. 待确认 / 开放问题

- 配置格式：已定 **YAML**（`config.yaml` / `rooms.yaml`，自愈 + 热重载）。
- 前端形态：原生静态页 + 自托管 `mpegts.js`（无框架，无第三方 CDN）。
- 鉴权：Web UI 暂不加登录（个人自用，后续可加）。
- 部署：已提供 Docker（`DOCKER.md`）、Windows 安装包（Inno Setup，CI 自动构建），以及 **桌面客户端**（Tauri 外壳 + 内置 Python 后端 sidecar，CI 构建 NSIS 安装包，见 §13）。
- 弹幕 X-Bogus 纯 Python 实现——**已落地**（见 §5）；V8 / `py-mini-racer` / `sign.js` 已彻底移除，打包无需收集原生 dll。

---

## 13. 桌面客户端（M8，Tauri）

> 用户需要的是**独立客户端**，而非「本地起服务再开 localhost 浏览器」。参考存档 `rust-srec` 的 Tauri 架构实现。

### 13.1 运行模型（对齐 rust-srec，后端为 sidecar 而非 in-process）

`rust-srec` 的 Tauri 外壳把 Rust 后端 **in-process** 启动、webview 加载构建好的前端、注入后端地址；Dy-Sentry 后端是 Python，无法直接塞进 Rust，因此改为把 PyInstaller 冻结的 Python 后端作为 **Tauri sidecar** 启动，webview 直接加载后端提供的页面。流程：

1. 启动显示启动屏（加载 `desktop/frontend/index.html`）；
2. 以 Tauri app data 目录为 `cwd` 拉起 Python 后端（`dy-sentry.exe`，即 `run.py` 的 uvicorn 服务）作为 sidecar；
3. 轮询 `127.0.0.1:12580/health`（新增于 `src/api/app.py`），就绪后打开主窗口指向 `http://127.0.0.1:12580/manage`（监控 / 录制核心）；
4. 系统托盘、单实例（第二次启动聚焦已有窗口）、关闭最小化到托盘；退出时杀掉 sidecar 进程树（含 ffmpeg 子进程）。

### 13.2 目录与关键文件

- `desktop/src-tauri/tauri.conf.json`：`productName` / `identifier` / `bundle.targets=["nsis"]` / `externalBin: ["../binaries/dy-sentry"]` / `security.csp` 放行 `127.0.0.1:*`。
- `desktop/src-tauri/src/lib.rs`：启动、sidecar 拉起、端口轮询、主窗口、托盘、单实例、优雅退出。
- `desktop/src-tauri/capabilities/default.json`：窗口 `main`/`splash` 的权限（`shell:allow-execute` 等）。
- `desktop/src-tauri/frontend/index.html`：启动屏。
- `desktop/binaries/`：CI 构建期放入 `dy-sentry-x86_64-pc-windows-msvc.exe`（PyInstaller 产物重命名），不进仓库。

### 13.3 数据落点与前端

- sidecar `cwd` = Tauri app data 目录 → `config.yaml` / `rooms.yaml` / `recordings/` 落于应用数据目录，升级不丢。
- 前端复用现有 `src/web`（管理页 / 预览页），webview **直接加载后端页面**（同源，无需改前端）；**默认进管理页，预览作为次级入口**——呼应「监控+录制是核心，直播预览只是场景之一」。

### 13.4 构建与边界

- CI `.github/workflows/build-desktop.yml`（windows-latest）：PyInstaller 出 sidecar → 重命名放入 `desktop/binaries/` → `cargo tauri build` 出 NSIS 安装包。
- 本机 macOS 无法本地验证 Tauri 构建（无 Rust / Windows 工具链），以 CI 为准；产物未做代码签名，Windows SmartScreen 可能告警（需 EV 证书 + secrets 可后续补）。
