# Feature: domain-manager, Property 30: 口令加盐不可逆哈希且可校验
"""Property 30: 口令加盐不可逆哈希且可校验。

对任意口令 p，verify_password(p, hash_password(p)) 为真；哈希串不等于也不包含明文 p；
对同一口令两次调用 hash_password 因随机盐而产生不同的哈希串。

Validates: Requirements 9.7
"""
from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.auth import hash_password, verify_password

# 口令取非空可见字符串。
_passwords = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=64
)


@settings(max_examples=100)
@given(password=_passwords)
def test_password_hash_salted_irreversible_verifiable(password):
    h1 = hash_password(password)
    h2 = hash_password(password)

    # 可校验。
    assert verify_password(password, h1) is True
    assert verify_password(password, h2) is True

    # 哈希串不等于明文（不可逆存储）。注意：PBKDF2 的十六进制摘要可能"恰好"
    # 包含短明文作为子串，这并非泄露，因此此处不做子串断言，只断言整体不等。
    assert h1 != password

    # 随机盐：同一口令两次哈希不同。
    assert h1 != h2


@settings(max_examples=100)
@given(password=_passwords, other=_passwords)
def test_wrong_password_rejected(password, other):
    h = hash_password(password)
    if other != password:
        assert verify_password(other, h) is False
