"""ffmpeg 视频录制（M3）。

移植 DLR 的 ffmpeg 拉流参数与 h265→TS 容器回退；修复 STREAM1 的两个 bug：
- 录制意外退出后**重新拉取流地址**再重试（STREAM1 用过期 URL 无限重启）；
- 清晰度由 fetcher 解析后真正传入（STREAM1 里清晰度是死代码）。
分片用 ffmpeg 自带 segment muxer（按时长），避免监控线程重启进程的复杂度。
"""
from __future__ import annotations

import asyncio
import shutil
import urllib.parse
from pathlib import Path

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


def get_codec(url: str) -> str | None:
    """从流地址的 query 里取 codec 参数（如 h265）。"""
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    vals = qs.get("codec") or []
    return vals[0] if vals else None


def choose_container(url: str, prefer: str = "flv") -> str:
    """决定录制容器。FLV 装不下 h265 → 回退 TS（移植 DLR main.py:1232-1236）。"""
    prefer = (prefer or "flv").lower()
    if prefer == "flv" and get_codec(url) == "h265":
        return "ts"
    return prefer


def build_ffmpeg_cmd(
    url: str,
    out_path: str,
    *,
    user_agent: str = MOBILE_UA,
    cookie: str | None = None,
    referer: str | None = None,
    container: str = "flv",
    segment_seconds: int | None = None,
) -> list[str]:
    """构建 ffmpeg 拉流命令（-c copy 不转码）。headers 以 -headers 传入。"""
    cmd = [
        "ffmpeg", "-y",
        "-loglevel", "error",
        "-hide_banner",
        "-user_agent", user_agent,
        "-protocol_whitelist", "rtmp,crypto,file,http,https,tcp,tls,udp,rtp,httpproxy",
        "-thread_queue_size", "1024",
        "-analyzeduration", "20000000",
        "-probesize", "10000000",
        "-fflags", "+discardcorrupt",
        "-re", "-i", url,
        "-bufsize", "8000k",
        "-sn", "-dn",
        "-reconnect_delay_max", "60",
        "-reconnect_streamed", "-reconnect_at_eof",
        "-max_muxing_queue_size", "1024",
        "-correct_ts_overflow", "1",
        "-avoid_negative_ts", "1",
        "-c", "copy",
    ]
    headers = ""
    if cookie:
        headers += f"Cookie: {cookie}\r\n"
    if referer:
        headers += f"Referer: {referer}\r\n"
    if headers:
        # -headers 需紧跟输入选项之前；放在 -i 前
        idx = cmd.index("-i")
        cmd[idx:idx] = ["-headers", headers]

    if segment_seconds:
        cmd += [
            "-f", "segment",
            "-segment_time", str(segment_seconds),
            "-segment_format", container,
            "-reset_timestamps", "1",
            out_path.replace(".", "_%03d.", 1),
        ]
    else:
        cmd += ["-f", container, out_path]
    return cmd


def build_remux_cmd(src: str, dst: str) -> list[str]:
    """FLV/TS → MP4 转封装（-c copy 无损，+faststart 便于拖动）。"""
    return [
        "ffmpeg", "-y",
        "-loglevel", "error",
        "-hide_banner",
        "-i", src,
        "-c", "copy",
        "-movflags", "+faststart",
        dst,
    ]


class VideoRecorder:
    """单个房间的 ffmpeg 录制任务。

    refresh: 可选异步回调，返回最新流地址；录制意外退出时用它重新拉地址再重试
    （修 STREAM1 用过期 URL 无限重启的 bug）。
    """

    def __init__(
        self,
        url: str,
        out_path: str,
        *,
        cookie: str | None = None,
        referer: str | None = None,
        user_agent: str = MOBILE_UA,
        container: str | None = None,
        remux_mp4: bool = True,
        segment_seconds: int | None = None,
        refresh=None,
        max_retries: int = 3,
    ):
        self.url = url
        self.out_path = out_path
        self.cookie = cookie
        self.referer = referer
        self.user_agent = user_agent
        self.container = container or choose_container(url)
        self.remux_mp4 = remux_mp4
        self.segment_seconds = segment_seconds
        self.refresh = refresh
        self.max_retries = max_retries
        self._proc: asyncio.subprocess.Process | None = None
        self._stopped = False

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> int:
        """启动录制并阻塞到停止/结束。返回重试次数用尽后的退出码。"""
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg not found in PATH")
        attempts = 0
        while not self._stopped and attempts <= self.max_retries:
            cmd = build_ffmpeg_cmd(
                self.url, self.out_path,
                user_agent=self.user_agent, cookie=self.cookie, referer=self.referer,
                container=self.container, segment_seconds=self.segment_seconds,
            )
            self._proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            code = await self._proc.wait()
            self._proc = None
            if self._stopped:
                break
            # 意外退出：重新拉取流地址再重试（修 STREAM1 bug）
            attempts += 1
            if self.refresh:
                new_url = await self.refresh()
                if new_url:
                    self.url = new_url
                    self.container = self.container or choose_container(new_url)
            await asyncio.sleep(min(2 ** attempts, 30))
        if self.remux_mp4 and not self.segment_seconds and Path(self.out_path).exists():
            await self.remux()
        return attempts

    async def remux(self) -> Path | None:
        src = Path(self.out_path)
        dst = src.with_suffix(".mp4")
        proc = await asyncio.create_subprocess_exec(
            *build_remux_cmd(str(src), str(dst)),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        code = await proc.wait()
        if code == 0 and dst.exists():
            src.unlink(missing_ok=True)
            return dst
        return None

    async def stop(self) -> None:
        """优雅停止：SIGINT 让 ffmpeg 写好文件头；超时再 kill。"""
        self._stopped = True
        if self._proc and self._proc.returncode is None:
            self._proc.send_signal(2)  # SIGINT
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=10)
            except asyncio.TimeoutError:
                self._proc.kill()
