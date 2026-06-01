"""域名状态计算纯函数（需求 2）。

剩余天数与状态都是无副作用的纯函数，便于属性测试。
注意 design.md 中明确了两种"剩余天数"口径：
- status_remaining_days：向下取整、可为负，用于状态计算与列表展示（需求 2.3）。
- 提醒展示剩余天数：向上取整、最小 0，见 notification 模块（需求 4.3）。
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from .models import DomainStatus


def status_remaining_days(expiration_date: Optional[date], today: date) -> Optional[int]:
    """计算到期剩余整日历日（需求 2.3）。

    = (expiration_date - today) 的天数差，向下取整到整日历日，可为负。
    到期时间为空时返回 None。
    """
    if expiration_date is None:
        return None
    return (expiration_date - today).days


def compute_status(
    expiration_date: Optional[date],
    today: date,
    max_threshold: int,
) -> DomainStatus:
    """根据到期时间计算 Domain_Status（需求 2.6/2.7/2.8/2.9）。

    - 到期时间为空 -> Active（需求 2.9，另由上层附加"缺失"可见标识）。
    - 剩余天数 d < 0 -> Expired（需求 2.6）。
    - 0 <= d <= max_threshold -> Expiring（需求 2.7）。
    - d > max_threshold -> Active（需求 2.8）。
    """
    if expiration_date is None:
        return DomainStatus.ACTIVE
    d = status_remaining_days(expiration_date, today)
    if d < 0:
        return DomainStatus.EXPIRED
    if d <= max_threshold:
        return DomainStatus.EXPIRING
    return DomainStatus.ACTIVE
