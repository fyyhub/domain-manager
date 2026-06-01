"""凭证加密/解密与掩码工具（需求 7.6、8.6）。

使用 cryptography 的 Fernet（AES-128-CBC + HMAC）对称加密 Cloudflare 凭证与
SMTP 凭据。加密主密钥来自部署环境变量 DM_ENCRYPTION_KEY；测试时可显式传入。

设计要点：
- 存储时加密、使用时解密、界面只显示掩码（需求 7.6/8.6）。
- 同一明文每次加密产生不同密文（Fernet 含随机 IV 与时间戳），但都能解回原文。
"""
from __future__ import annotations

import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

ENV_KEY = "DM_ENCRYPTION_KEY"


def generate_key() -> str:
    """生成一个新的 Fernet 主密钥（base64 字符串）。供首次部署使用。"""
    return Fernet.generate_key().decode("ascii")


def _resolve_key(key: Optional[str]) -> bytes:
    raw = key if key is not None else os.environ.get(ENV_KEY)
    if not raw:
        raise RuntimeError(
            f"缺少加密主密钥：请设置环境变量 {ENV_KEY}（可用 crypto.generate_key() 生成）"
        )
    if isinstance(raw, str):
        raw = raw.encode("ascii")
    return raw


def encrypt_credential(plaintext: str, key: Optional[str] = None) -> bytes:
    """加密凭证明文，返回密文字节（需求 7.6）。"""
    f = Fernet(_resolve_key(key))
    return f.encrypt(plaintext.encode("utf-8"))


def decrypt_credential(token: bytes, key: Optional[str] = None) -> Optional[str]:
    """解密凭证密文；密钥不符或密文损坏返回 None。"""
    if token is None:
        return None
    f = Fernet(_resolve_key(key))
    try:
        return f.decrypt(token).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def mask_credential(plaintext: Optional[str]) -> str:
    """生成凭证掩码用于界面展示，绝不回显明文（需求 7.6/8.6）。

    保留末尾最多 4 个字符，其余以圆点遮蔽；空值返回空掩码。
    """
    if not plaintext:
        return ""
    tail = plaintext[-4:] if len(plaintext) >= 4 else plaintext
    return "••••" + tail
