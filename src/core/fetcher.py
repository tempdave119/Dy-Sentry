"""Dy 房间信息与拉流地址抓取。

设计要点（见 docs/architecture.md §5/§7）：
- HTTP API 用纯 Python a_bogus 签名（core.ab_sign）。
- 纯逻辑（URL 解析、ORIGIN 前置、清晰度选择）与网络层分离，便于离线单测。
- Cookie 一律由调用方注入（来自配置），源码不内置任何 cookie/token（红线）。
- 三级回退中的主路径=web enter API，次路径=房间页 HTML 正则；短链 app/reflow 路径留待后续。
"""
from __future__ import annotations

import json
import re
import urllib.parse

import httpx

from .ab_sign import ab_sign

LIVE_HOST = "live.douyin.com"
ENTER_API = f"https://{LIVE_HOST}/webcast/room/web/enter/"
DEFAULT_REFERER = f"https://{LIVE_HOST}/"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/116.0.5845.97 Safari/537.36"
)

# 清晰度档位 → 流地址列表下标（ORIGIN 原画经前置后为下标 0）
QUALITY_MAPPING = {"OD": 0, "BD": 0, "UHD": 1, "HD": 2, "SD": 3, "LD": 4}

# 无用户 cookie 时，用首页种下的 ttwid 作为基础 cookie（enter API 无 cookie 会被风控返回空 body）
_BASE_COOKIE: str | None = None


async def ensure_base_cookie(client: httpx.AsyncClient) -> str:
    global _BASE_COOKIE
    if _BASE_COOKIE:
        return _BASE_COOKIE
    await client.get(f"https://{LIVE_HOST}/", headers={"user-agent": DEFAULT_UA})
    ttwid = client.cookies.get("ttwid")
    if ttwid:
        _BASE_COOKIE = f"ttwid={ttwid}"
    return _BASE_COOKIE or ""


def parse_web_rid(url: str) -> str | None:
    """取出 web_rid。支持两种形式：
    - 路径形式 https://live.douyin.com/<web_rid>
    - 查询参数形式 https://live.douyin.com/?live_web_rid=<web_rid>（也兼容 web_rid/room_id）
    非该直播域返回 None。
    """
    if LIVE_HOST not in url:
        return None
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    for key in ("live_web_rid", "web_rid", "room_id"):
        if qs.get(key, [""])[0]:
            return qs[key][0]
    return parsed.path.strip("/") or None


def quality_index(quality: str | int | None) -> tuple[str, int]:
    """把用户配置的清晰度归一为 (档位名, 列表下标)。"""
    if not quality:
        return "OD", 0
    q = str(quality).upper()
    if q.isdigit():
        q = list(QUALITY_MAPPING)[int(q[0])]
    return q, QUALITY_MAPPING.get(q, 0)


def prepend_origin(room_data: dict) -> None:
    """若存在原画(ORIGIN)流，把它前置进 flv/m3u8 映射，使下标 0=原画。就地修改 room_data。

    移植自 DLR:src/spider.py 的 origin 前置逻辑：原画地址藏在双层 JSON 编码的
    live_core_sdk_data.pull_data.stream_data 里，需解出后插到映射最前。
    """
    stream_url = room_data.get("stream_url")
    if not stream_url:
        return
    live_core_sdk_data = stream_url.get("live_core_sdk_data")
    if not live_core_sdk_data:
        return
    pull_datas = stream_url.get("pull_datas")
    if pull_datas:
        first_key = list(pull_datas.keys())[0]
        json_str = pull_datas[first_key]["stream_data"]
    else:
        json_str = live_core_sdk_data["pull_data"]["stream_data"]
    parsed = json.loads(json_str)
    if "origin" not in parsed.get("data", {}):
        return

    origin_main = parsed["data"]["origin"]["main"]
    sdk_params = json.loads(origin_main["sdk_params"])
    codec = sdk_params.get("VCodec") or ""
    origin_m3u8 = {"ORIGIN": origin_main["hls"] + "&codec=" + codec}
    origin_flv = {"ORIGIN": origin_main["flv"] + "&codec=" + codec}
    stream_url["hls_pull_url_map"] = {**origin_m3u8, **stream_url.get("hls_pull_url_map", {})}
    stream_url["flv_pull_url"] = {**origin_flv, **stream_url.get("flv_pull_url", {})}


def build_stream_lists(room_data: dict) -> tuple[list[str], list[str]]:
    """取出 flv/m3u8 地址列表并补齐到 5 档（不足复制末位）。返回 (flv_list, m3u8_list)。"""
    stream_url = room_data["stream_url"]
    flv_list = list(stream_url["flv_pull_url"].values())
    m3u8_list = list(stream_url["hls_pull_url_map"].values())
    while len(flv_list) < 5 and flv_list:
        flv_list.append(flv_list[-1])
        m3u8_list.append(m3u8_list[-1])
    return flv_list, m3u8_list


def select_quality(flv_list: list[str], m3u8_list: list[str], quality: str | int | None) -> dict:
    """按配置清晰度选档，返回 {quality, flv_url, m3u8_url}（不做网络探测）。"""
    name, idx = quality_index(quality)
    return {
        "quality": name,
        "flv_url": flv_list[idx],
        "m3u8_url": m3u8_list[idx],
    }


def _enter_url(web_rid: str) -> str:
    params = {
        "aid": "6383",
        "app_name": "douyin_web",
        "live_id": "1",
        "device_platform": "web",
        "language": "zh-CN",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Chrome",
        "browser_version": "116.0.0.0",
        "web_rid": web_rid,
        "msToken": "",
    }
    api = f"{ENTER_API}?{urllib.parse.urlencode(params)}"
    return api, urllib.parse.urlparse(api).query


async def fetch_web_room_data(
    web_rid: str,
    *,
    cookie: str | None = None,
    user_agent: str = DEFAULT_UA,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """调用 web enter API 取房间数据，返回 room_data（含 anchor_name）。失败抛异常。"""
    api, query = _enter_url(web_rid)

    own = client is None
    client = client or httpx.AsyncClient(timeout=15.0)
    try:
        cookie = cookie or await ensure_base_cookie(client)
        headers = {
            "referer": f"{DEFAULT_REFERER}{web_rid}",
            "user-agent": user_agent,
        }
        if cookie:
            headers["cookie"] = cookie

        # 默认不带 a_bogus：存档的 a_bogus 算法已被平台更新淘汰，带签名反而被拒返回空 body。
        # 仅当无签名请求被风控（空 body）时，回退带签名重试一次。
        resp = await client.get(api, headers=headers)
        if not resp.text:
            resp = await client.get(api + "&a_bogus=" + ab_sign(query, user_agent), headers=headers)
        resp.raise_for_status()
        payload = resp.json()["data"]
        if not payload.get("data"):
            raise RuntimeError("empty room data (可能被风控或不支持的直播类型)")
        room_data = payload["data"][0]
        room_data["anchor_name"] = payload["user"]["nickname"]
        return room_data
    finally:
        if own:
            await client.aclose()


async def probe_url_ok(
    url: str,
    *,
    referer: str = DEFAULT_REFERER,
    cookie: str | None = None,
    user_agent: str = DEFAULT_UA,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """GET 探测流地址是否可达（用于清晰度降级判断）。httpx 0.28 用 stream() 取代 get(stream=True)。"""
    own = client is None
    client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=True)
    try:
        headers = {"referer": referer, "user-agent": user_agent}
        if cookie:
            headers["cookie"] = cookie
        async with client.stream("GET", url, headers=headers) as resp:
            return resp.status_code == 200
    except httpx.HTTPError:
        return False
    finally:
        if own:
            await client.aclose()


async def check_live_status(
    url: str,
    *,
    quality: str | int | None = "OD",
    cookie: str | None = None,
    user_agent: str = DEFAULT_UA,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """检查房间开播状态并解析拉流地址。

    返回 {is_live, anchor_name, title?, quality?, m3u8_url?, flv_url?, record_url?, room_id?}。
    未开播或解析失败时 is_live=False。
    """
    web_rid = parse_web_rid(url)
    if not web_rid:
        return {"is_live": False, "anchor_name": None, "error": "unsupported url (需 live 房间页 URL)"}

    own = client is None
    client = client or httpx.AsyncClient(timeout=15.0)
    try:
        try:
            room_data = await fetch_web_room_data(web_rid, cookie=cookie, user_agent=user_agent, client=client)
        except Exception as e:  # noqa: BLE001 - 主路径失败时降级
            return {"is_live": False, "anchor_name": None, "error": f"web enter failed: {e}"}

        result: dict = {
            "is_live": False,
            "anchor_name": room_data.get("anchor_name"),
            "room_id": room_data.get("id_str"),
        }
        if room_data.get("status") != 2:
            return result

        prepend_origin(room_data)
        if "stream_url" not in room_data:
            result["error"] = "no stream_url (该直播类型电脑端暂不支持)"
            return result

        flv_list, m3u8_list = build_stream_lists(room_data)
        sel = select_quality(flv_list, m3u8_list, quality)
        # HEAD 探测 m3u8，不可达则降级到相邻档（移植 DLR stream.py 逻辑）
        name, idx = quality_index(quality)
        if not await probe_url_ok(sel["m3u8_url"], cookie=cookie, client=client):
            alt = idx + 1 if idx < 4 else idx - 1
            sel = {
                "quality": list(QUALITY_MAPPING)[alt] if alt < len(QUALITY_MAPPING) else name,
                "flv_url": flv_list[alt],
                "m3u8_url": m3u8_list[alt],
            }
        result |= {
            "is_live": True,
            "title": room_data.get("title"),
            "quality": sel["quality"],
            "m3u8_url": sel["m3u8_url"],
            "flv_url": sel["flv_url"],
            "record_url": sel["m3u8_url"] or sel["flv_url"],
        }
        return result
    finally:
        if own:
            await client.aclose()
