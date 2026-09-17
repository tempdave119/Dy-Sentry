"""Dy 弹幕源（M4）：WebSocket + Protobuf 解码，产出统一消息字典。

设计要点：
- 签名用**纯 Python X-Bogus**（core.ws_signer，移植 SREC 当前算法）；弹幕 WS 升级必须带
  signature（无签名服务器回 HTTP 200 拒绝升级）。已弃用存档的 V8/sign.js（被淘汰）。
- 握手头需 Origin + User-Agent + Cookie(ttwid)；ttwid 复用 fetcher 的自动种 cookie。
- query 参数集与 TLS context 对齐 SREC（certifi 证书包，WSS 主机链含自签根）。
- 心跳 + ACK + 指数退避重连（补存档缺的重连）。
"""
from __future__ import annotations

import asyncio
import gzip
import random
import ssl
import time
import urllib.parse
from collections.abc import AsyncIterator

import certifi
import httpx
import websockets

from core import fetcher
from core.proto import douyin_pb as pb
from core.ws_signer import VERSION_CODE, WEBCAST_SDK_VERSION, generate_ws_signature

WSS_HOST = "webcast100-ws-web-lq.douyin.com"
LIVE_HOST = "live.douyin.com"

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _rand_id() -> str:
    return str(random.randint(7_000_000_000_000_000_000, 7_999_999_999_999_999_999))


def _browser_version() -> str:
    return DEFAULT_UA.split("Chrome/")[-1].split(" ")[0]


def build_wss_url(room_id: str, user_id: str) -> str:
    """构建弹幕 WSS 地址（不含 signature）。参数集对齐 SREC common+ws params。"""
    params = {
        # common params
        "app_name": "douyin_web",
        "compress": "gzip",
        "device_platform": "web",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Mozilla",
        "browser_version": _browser_version(),
        "aid": "6383",
        "live_id": "1",
        "enter_from": "web_live",
        # ws params
        "version_code": VERSION_CODE,
        "webcast_sdk_version": WEBCAST_SDK_VERSION,
        "update_version_code": WEBCAST_SDK_VERSION,
        "host": f"https://{LIVE_HOST}",
        "did_rule": "3",
        "identity": "audience",
        "endpoint": "live_pc",
        "need_persist_msg_count": "15",
        "heartbeatDuration": "0",
        "room_id": room_id,
        "user_unique_id": user_id,
    }
    return f"wss://{WSS_HOST}/webcast/im/push/v2/?{urllib.parse.urlencode(params)}"


def _ssl_context() -> ssl.SSLContext:
    """WSS 主机把自签根证书塞进链，本机默认 CA store 校验失败；用 certifi（含 DigiCert G2）。"""
    return ssl.create_default_context(cafile=certifi.where())


def _user_name(msg) -> str:
    user = getattr(msg, "user", None)
    return getattr(user, "nick_name", "") or ""


def decode_message(method: str, payload: bytes) -> dict | None:
    """把单条 protobuf 消息解码为统一字典 {type, user, content}；无法识别返回 None。"""
    try:
        if method == "WebcastChatMessage":
            m = pb.ChatMessage().parse(payload)
            return {"type": "chat", "user": _user_name(m), "content": m.content}
        if method == "WebcastGiftMessage":
            m = pb.GiftMessage().parse(payload)
            gift = getattr(m, "gift", None)
            name = getattr(gift, "name", "") or f"gift#{m.gift_id}"
            count = m.repeat_count or m.combo_count or 1
            return {"type": "gift", "user": _user_name(m), "content": f"{name} x{count}"}
        if method == "WebcastLikeMessage":
            m = pb.LikeMessage().parse(payload)
            return {"type": "like", "user": _user_name(m), "content": str(m.count or 1)}
        if method == "WebcastMemberMessage":
            m = pb.MemberMessage().parse(payload)
            return {"type": "enter", "user": _user_name(m), "content": ""}
        if method == "WebcastSocialMessage":
            m = pb.SocialMessage().parse(payload)
            return {"type": "follow", "user": _user_name(m), "content": ""}
        if method == "WebcastRoomUserSeqMessage":
            m = pb.RoomUserSeqMessage().parse(payload)
            return {"type": "stats", "user": "", "content": str(getattr(m, "total", 0))}
        if method == "WebcastControlMessage":
            m = pb.ControlMessage().parse(payload)
            return {"type": "control", "user": "", "content": str(m.status)}
    except Exception:  # noqa: BLE001 - 单条解码失败不影响整体
        return None
    return None


async def _base_cookie() -> str | None:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        return await fetcher.ensure_base_cookie(client) or None


async def iter_danmaku(
    room_id: str,
    *,
    cookie: str | None = None,
    user_agent: str = DEFAULT_UA,
    reconnect: bool = True,
    max_backoff: float = 60.0,
) -> AsyncIterator[dict]:
    """连接弹幕 WS 并持续产出消息字典；断线按指数退避重连。"""
    user_id = _rand_id()
    base_url = build_wss_url(room_id, user_id)
    url = base_url + "&signature=" + generate_ws_signature(room_id, user_id)

    cookie = cookie or await _base_cookie()
    headers = {
        "origin": f"https://{LIVE_HOST}",
        "user-agent": user_agent,
    }
    if cookie:
        headers["cookie"] = cookie

    backoff = 1.0
    while True:
        try:
            async with websockets.connect(
                url, additional_headers=headers, ping_interval=None, ssl=_ssl_context()
            ) as ws:
                backoff = 1.0  # 连上即重置退避

                async def heartbeat():
                    while True:
                        await asyncio.sleep(5)
                        await ws.send(pb.PushFrame(payload_type="hb").SerializeToString())

                hb = asyncio.create_task(heartbeat())
                try:
                    async for raw in ws:
                        frame = pb.PushFrame().parse(raw)
                        if not frame.payload:
                            continue
                        try:
                            payload = gzip.decompress(frame.payload)
                        except OSError:
                            payload = frame.payload
                        resp = pb.Response().parse(payload)
                        if resp.need_ack:
                            ack = pb.PushFrame(
                                log_id=frame.log_id,
                                payload_type="ack",
                                payload=resp.internal_ext.encode("utf-8"),
                            )
                            await ws.send(ack.SerializeToString())
                        for msg in resp.messages_list:
                            d = decode_message(msg.method, msg.payload)
                            if d:
                                d["ts"] = _now_ms()
                                yield d
                finally:
                    hb.cancel()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - 连接/解码异常 → 重连
            if not reconnect:
                raise
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
