"""Notification_Channel 抽象与提醒内容构造（需求 4.3、4.5）。

定义渠道接口与提醒载荷，并实现提醒展示用的剩余天数计算
（max(0, ceil(Expiration_Date − today))，需求 4.3）与内容渲染。
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional


def reminder_remaining_days(expiration_date: Optional[date], today: date) -> int:
    """提醒展示用剩余天数：向上取整、最小 0（需求 4.3）。

    与状态计算用的 status_remaining_days（向下取整、可为负）不同，
    此口径用于通知文案，确保不出现负数。
    """
    if expiration_date is None:
        return 0
    delta_days = (expiration_date - today).days
    # 整日差本身即整数；ceil 在此等价，但保留语义并对最小值裁剪到 0。
    return max(0, math.ceil(delta_days))


@dataclass
class ReminderPayload:
    """一条提醒的载荷（需求 4.3）。"""

    domain_name: str
    expiration_date: Optional[date]
    remaining_days: int
    kind: str = "expiring"  # "expiring" | "expired"

    def render_subject(self) -> str:
        if self.kind == "expired":
            return f"[域名管理] 域名已过期：{self.domain_name}"
        return f"[域名管理] 域名临近到期：{self.domain_name}（剩余 {self.remaining_days} 天）"

    def render_body(self) -> str:
        exp = self.expiration_date.isoformat() if self.expiration_date else "未设置"
        return (
            f"域名：{self.domain_name}\n"
            f"到期时间：{exp}\n"
            f"剩余天数：{self.remaining_days} 天\n"
        )


@dataclass
class ChannelResult:
    """渠道发送结果。"""

    ok: bool
    message: str = ""


class NotificationChannel(ABC):
    """通知渠道抽象接口。"""

    name: str = "channel"

    @abstractmethod
    def is_enabled(self) -> bool:
        ...

    @abstractmethod
    def send(self, payload: ReminderPayload) -> ChannelResult:
        ...


def build_payload(
    domain_name: str,
    expiration_date: Optional[date],
    today: date,
    kind: str = "expiring",
) -> ReminderPayload:
    """根据域名信息构造提醒载荷（需求 4.3）。"""
    return ReminderPayload(
        domain_name=domain_name,
        expiration_date=expiration_date,
        remaining_days=reminder_remaining_days(expiration_date, today),
        kind=kind,
    )
