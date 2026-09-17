"""a_bogus 签名单测。可 pytest 运行，也可 `PYTHONPATH=src python3 tests/test_ab_sign.py` 直接运行。"""
from core.ab_sign import SM3, rc4_encrypt, generate_random_str, ab_sign

S4_TABLE = "Dkdpgh2ZmsQB80/MfvV36XI1R45-WUAlEixNLwoqYTOPuzKFjJnry79HbGcaStCe="


def test_sm3_known_vectors():
    # 标准 SM3 测试向量
    assert SM3().sum("abc", "hex") == \
        "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"
    assert SM3().sum("", "hex") == \
        "1ab21d8355cfa17f8e61194831e81a8f22bec8c728fefb747ed035eb5082aa2b"


def test_rc4_is_symmetric():
    key = "secret-key"
    plain = "hello-a_bogus-payload"
    assert rc4_encrypt(rc4_encrypt(plain, key), key) == plain


def test_generate_random_str_is_deterministic():
    a = generate_random_str()
    b = generate_random_str()
    assert a == b            # 固定随机值 → 可复现
    assert len(a) == 12      # 三组各 4 字节


def test_ab_sign_format():
    sig = ab_sign("aid=6383&app_name=dy_web&room_id=123456", "Mozilla/5.0")
    assert isinstance(sig, str)
    assert sig.endswith("=")
    assert len(sig) > 50
    assert all(c in S4_TABLE for c in sig)


def test_ab_sign_prefix_stable():
    # 前 12 字节来自固定随机前缀 → 输出前 16 字符与时间戳无关，应稳定
    q = "aid=6383&room_id=123456"
    ua = "Mozilla/5.0"
    assert ab_sign(q, ua)[:16] == ab_sign(q, ua)[:16]


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
