"""域名名称与到期时间校验纯函数（需求 1.6、1.7）。

这些函数无副作用，便于属性测试覆盖（见 design.md Testing Strategy）。
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional, Union

# 域名标签：字母数字开头结尾，中间可含连字符，1–63 字符。
_LABEL = r"(?!-)[A-Za-z0-9-]{1,63}(?<!-)"
# 完整域名：至少两个点（三级域名，如 sub.example.com），各标签符合 _LABEL。
_DOMAIN_RE = re.compile(
    rf"^{_LABEL}(?:\.{_LABEL})+$"
)

MAX_DOMAIN_LENGTH = 253
MIN_DOMAIN_LENGTH = 1
# 三级域名至少包含 3 段（label.label.label）。
MIN_LABELS_FOR_THIRD_LEVEL = 3


def is_valid_domain_name(name: object) -> bool:
    """判断 name 是否为合法的三级域名（需求 1.6）。

    规则：
    - 必须为字符串；
    - 长度 1–253（含两端）；
    - 整体符合域名格式（各标签合法、点分隔）；
    - 至少 3 段（三级域名，如 a.b.c）。
    """
    if not isinstance(name, str):
        return False
    if not (MIN_DOMAIN_LENGTH <= len(name) <= MAX_DOMAIN_LENGTH):
        return False
    if not _DOMAIN_RE.match(name):
        return False
    if name.count(".") < MIN_LABELS_FOR_THIRD_LEVEL - 1:
        return False
    return True


def is_valid_expiration_date(value: object) -> bool:
    """判断 value 是否为合法的到期日期（需求 1.7）。

    接受 date 实例，或可解析为合法日历日期的 ISO 格式字符串（YYYY-MM-DD）。
    空值（None / 空串）视为无效（创建时到期时间不可缺失，需求 1.7）。
    注意：需求 2.9 允许已有记录的到期时间为空并标记 Active，但创建输入要求非空合法日期。
    """
    if value is None:
        return False
    if isinstance(value, date):
        return True
    if isinstance(value, str):
        return parse_date(value) is not None
    return False


def parse_date(value: Union[str, date, None]) -> Optional[date]:
    """将 ISO 字符串解析为 date；已是 date 则原样返回；无法解析返回 None。"""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except (ValueError, TypeError):
            return None
    return None
