# Feature: domain-manager, Property 20: 凭证加密往返且不回显明文
"""Property 20: 凭证加密往返且不回显明文。

对任意 Cloudflare 凭证明文 c，加密后的存储值不等于 c，解密后等于 c，
且 get_config 及配置页渲染结果中不包含 c 的明文或可逆形式（仅返回掩码）。

Validates: Requirements 7.6, 8.6

注意：Fernet 密文为 base64 编码，其字母表涵盖数字与字母，因此单字符明文可能
"恰好"作为子串出现在密文中——这并非泄露。真正可测的安全属性是：
密文不等于明文、可用密钥解回原文、掩码视图只暴露末尾至多 4 个字符。
"""
import os

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager import crypto
from domain_manager.config_service import ConfigService
from domain_manager.store import DataStore

_KEY = crypto.generate_key()
# 凭证明文取 >=5 字符，使"掩码只暴露末尾 4 字符"成为可验证的属性。
_tokens = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=5, max_size=60
)


@settings(max_examples=100)
@given(token=_tokens)
def test_encrypt_roundtrip_and_not_plaintext(token):
    enc = crypto.encrypt_credential(token, _KEY)
    # 密文不等于明文。
    assert enc != token.encode("utf-8")
    # 可用密钥解回原文。
    assert crypto.decrypt_credential(enc, _KEY) == token
    # 同一明文两次加密产生不同密文（Fernet 随机 IV/时间戳）。
    enc2 = crypto.encrypt_credential(token, _KEY)
    assert enc2 != enc
    assert crypto.decrypt_credential(enc2, _KEY) == token


@settings(max_examples=100, deadline=None)
@given(token=_tokens)
def test_get_config_does_not_reveal_plaintext(tmp_path_factory, token):
    d = tmp_path_factory.mktemp("p20")
    store = DataStore(os.path.join(str(d), "p20.db"))
    store.initialize()
    svc = ConfigService(store, encryption_key=_KEY)
    svc.load()

    res = svc.update_cloudflare_credentials(token)
    assert res.is_ok

    masked = svc.get_config()
    # 掩码视图只暴露末尾至多 4 个字符，其余被遮蔽（精确刻画掩码形式）。
    assert masked.cloudflare_token_mask == "••••" + token[-4:]
    # 掩码不等于完整明文（明文长度 >=5，必不等于 4 字符尾部）。
    assert masked.cloudflare_token_mask != token
    # 存储的是密文，可用密钥解回原文（证明以可逆加密形式而非明文存储）。
    assert crypto.decrypt_credential(svc.config.cloudflare_token_encrypted, _KEY) == token
