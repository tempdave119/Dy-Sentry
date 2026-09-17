"""弹幕 WebSocket 签名（X-Bogus）——纯 Python 实现。

移植自 SREC（rust-srec，2026-09 仍活跃维护）`crates/.../douyin/signature.rs` 的
`generate_xbogus`：RC4 + 自定义字母表 base64，**无需 V8/sign.js**。
（存档 DANMU 的 sign.js/JSVMP 与 a_bogus 一样已被平台淘汰；SREC 的纯实现为当前可用算法。）

签名输入 = md5(固定顺序参数串)，counter 恒为 1。
"""
from __future__ import annotations

import base64
import hashlib
import random

XBOGUS_ALPHABET = "Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe"
STD_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_LOOKUP = str.maketrans(STD_ALPHABET, XBOGUS_ALPHABET)

# md5(decode(md5(''))) 的末两字节（SREC 预计算常量）
EMPTY_MD5_BYTES = (0x45, 0x3F)

VERSION_CODE = "180800"
WEBCAST_SDK_VERSION = "1.0.15"


def _rc4(key: int, data: bytearray) -> None:
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key) % 256
        s[i], s[j] = s[j], s[i]
    ii = 0
    j = 0
    for k in range(len(data)):
        ii = (ii + 1) % 256
        j = (j + s[ii]) % 256
        s[ii], s[j] = s[j], s[ii]
        data[k] ^= s[(s[ii] + s[j]) % 256]


def _md5_last2(hex32: str) -> tuple[int, int]:
    digest = hashlib.md5(bytes.fromhex(hex32)).digest()
    return digest[14], digest[15]


def xbogus(md5_hex: str, counter: int = 1) -> str:
    """由 32 位 hex 的 md5 生成 16 字符 X-Bogus 签名。"""
    random1 = random.randint(0, 255)
    random2 = (random.randint(0, 255) * 255 // 256) & 0xFF
    header = 0x40 | (random1 & 0x1F)

    mb = _md5_last2(md5_hex)
    payload = bytearray([
        counter & 0x3F,   # platform(0)<<6 | counter
        0,                # envcode >> 8
        1,                # envcode & 0xff
        0x0E,             # ubcode
        EMPTY_MD5_BYTES[0],
        EMPTY_MD5_BYTES[1],
        mb[0],
        mb[1],
        random2,
        0,                # checksum 占位
    ])
    checksum = 0
    for v in payload[:9]:
        checksum ^= v
    payload[9] = checksum

    _rc4(random2, payload)

    final = bytes([header, random2]) + bytes(payload)   # 12 bytes
    return base64.b64encode(final).decode().translate(_LOOKUP)


def ws_signature_param(room_id: str, user_id: str) -> str:
    """参与 md5 的固定顺序参数串（与 SREC/DANMU 一致）。"""
    return (
        f"live_id=1,aid=6383,version_code={VERSION_CODE},"
        f"webcast_sdk_version={WEBCAST_SDK_VERSION},"
        f"room_id={room_id},sub_room_id=,sub_channel_id=,did_rule=3,"
        f"user_unique_id={user_id},device_platform=web,device_type=,ac=,"
        f"identity=audience"
    )


def generate_ws_signature(room_id: str, user_id: str) -> str:
    """由 room_id + user_id 生成弹幕 WS 的 signature 参数值。"""
    param = ws_signature_param(room_id, user_id)
    return xbogus(hashlib.md5(param.encode()).hexdigest(), 1)
