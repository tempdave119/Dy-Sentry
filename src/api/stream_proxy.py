"""直播流后端代理。

为什么需要（docs/architecture.md §4）：浏览器直链 CDN 流地址无法自定义请求头，
header-gated 的流会被拒。后端代理可注入 Referer/Cookie/UA，把 FLV 字节流转发给前端播放器。
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/116.0.5845.97 Safari/537.36"
)


def _headers(referer: str, cookie: str | None, user_agent: str) -> dict[str, str]:
    h = {"referer": referer, "user-agent": user_agent}
    if cookie:
        h["cookie"] = cookie
    return h


async def iter_flv(
    stream_url: str,
    *,
    referer: str,
    cookie: str | None = None,
    user_agent: str = DEFAULT_UA,
) -> AsyncIterator[bytes]:
    """拉取远端 FLV 流并逐块产出字节；结束时关闭连接与客户端。"""
    client = httpx.AsyncClient(timeout=None, follow_redirects=True)
    try:
        req = client.build_request("GET", stream_url, headers=_headers(referer, cookie, user_agent))
        resp = await client.send(req, stream=True)
        resp.raise_for_status()
        try:
            async for chunk in resp.aiter_bytes(64 * 1024):
                if chunk:
                    yield chunk
        finally:
            await resp.aclose()
    finally:
        await client.aclose()
