"""ws_signer（纯 Python X-Bogus）单测。"""
from core.ws_signer import (
    XBOGUS_ALPHABET,
    _md5_last2,
    generate_ws_signature,
    ws_signature_param,
    xbogus,
)


def test_md5_last2_known_vector():
    # 向量来自 SREC signature.rs 的 test_md5_last2
    assert _md5_last2("56a634b4228ef02b53388ada4e6f76c7") == (0x26, 0x54)


def test_xbogus_format():
    sig = xbogus("56a634b4228ef02b53388ada4e6f76c7", 1)
    assert len(sig) == 16
    assert all(c in XBOGUS_ALPHABET for c in sig)


def test_signature_param_contains_ids():
    p = ws_signature_param("123", "456")
    assert "room_id=123," in p
    assert "user_unique_id=456," in p
    assert p.startswith("live_id=1,aid=6383,")


def test_generate_ws_signature_stable_shape():
    a = generate_ws_signature("123", "456")
    b = generate_ws_signature("123", "456")
    assert len(a) == 16 and len(b) == 16
    # 含随机字节，两次不必相等，但都必须是合法字母表
    assert all(c in XBOGUS_ALPHABET for c in a + b)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
