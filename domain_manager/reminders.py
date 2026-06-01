"""Reminder_Service：提醒计算、去重与重试（需求 3）。

纯函数 select_due_thresholds / should_send_expired 实现核心判定逻辑，便于属性测试；
run_reminder_check 负责加载、计算、多渠道发送与重试状态机。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

from .models import (
    DomainRecord,
    DomainStatus,
    ReminderSent,
    ReminderState,
)
from .notification import NotificationChannel, build_payload
from .status import status_remaining_days

# 最大重试次数（需求 3.5/4.7/4.8）。
MAX_RETRIES = 3
# 相邻发送尝试最小间隔（需求 4.7）。
MIN_RETRY_INTERVAL = timedelta(seconds=60)

EXPIRED_KEY = "expired"


def select_due_thresholds(
    record: DomainRecord,
    thresholds: List[int],
    sent_keys: set,
    today: date,
) -> List[int]:
    """计算某记录当前应触发的提醒阈值（需求 3.2）。

    对每个已配置阈值 t：当剩余整天数 ≤ t、且大于下一个更小的已配置阈值
    （若无更小阈值则剩余整天数 ≥ 0），且 (record.id, t) 尚未发送时，t 应触发。
    到期时间缺失（剩余为 None）不触发任何阈值提醒。
    """
    remaining = status_remaining_days(record.expiration_date, today)
    if remaining is None:
        return []
    # 已过期记录由 should_send_expired 处理，不在此触发档位提醒。
    if remaining < 0:
        return []

    ordered = sorted(set(thresholds))  # 升序
    due = []
    for t in ordered:
        # 下一个更小的已配置阈值。
        smaller = [x for x in ordered if x < t]
        lower_bound = max(smaller) if smaller else None
        in_band = remaining <= t and (lower_bound is None or remaining > lower_bound)
        if in_band and (record.id, t) not in sent_keys:
            due.append(t)
    return due


def should_send_expired(record: DomainRecord, today: date, expired_sent: bool) -> bool:
    """是否应发送过期提醒（需求 3.4）。

    记录已过期（剩余天数 < 0）且过期提醒尚未发送时为真；否则为假。
    """
    if expired_sent:
        return False
    remaining = status_remaining_days(record.expiration_date, today)
    if remaining is None:
        return False
    return remaining < 0


@dataclass
class ReminderRunSummary:
    """一次提醒检查的结果摘要。"""

    sent: int = 0
    failed: int = 0
    skipped: int = 0


class ReminderService:
    """提醒服务：协调阈值判定、去重、多渠道发送与重试。"""

    def __init__(
        self,
        store,
        domain_service,
        config_service,
        channels: List[NotificationChannel],
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self._store = store
        self._domain_service = domain_service
        self._config_service = config_service
        self._channels = channels
        self._clock = clock or datetime.now

    def _enabled_channels(self) -> List[NotificationChannel]:
        return [c for c in self._channels if c.is_enabled()]

    def _load_sent_index(self) -> Dict[Tuple[str, object], ReminderSent]:
        result = self._store.load_reminder_sent()
        index = {}
        if result.is_ok and result.value:
            for item in result.value:
                index[(item.domain_id, item.threshold)] = item
        return index

    def run_reminder_check(self, now: Optional[datetime] = None) -> ReminderRunSummary:
        """执行一次提醒检查（需求 3.2/3.3/3.4/3.5/4.6/4.7/4.8）。"""
        now = now or self._clock()
        today = now.date()
        summary = ReminderRunSummary()

        records = self._domain_service.list_domains()
        thresholds = self._config_service.config.reminder_thresholds
        sent_index = self._load_sent_index()

        # 已成功发送的键集合，用于去重判定。
        sent_keys = {
            key
            for key, item in sent_index.items()
            if item.state == ReminderState.SENT
        }

        for record in records:
            # 各档位到期提醒。
            for t in select_due_thresholds(record, thresholds, sent_keys, today):
                self._process_one(record, t, sent_index, now, summary, kind="expiring")

            # 过期提醒。
            expired_item = sent_index.get((record.id, EXPIRED_KEY))
            expired_sent = expired_item is not None and expired_item.state == ReminderState.SENT
            if should_send_expired(record, today, expired_sent):
                self._process_one(record, EXPIRED_KEY, sent_index, now, summary, kind="expired")

        return summary

    def _process_one(self, record, threshold, sent_index, now, summary, kind):
        """处理单条 (record, threshold) 的发送与重试状态机。"""
        item = sent_index.get((record.id, threshold))
        if item is None:
            item = ReminderSent(domain_id=record.id, threshold=threshold)
            sent_index[(record.id, threshold)] = item

        # 已达终态则跳过。
        if item.state in (ReminderState.SENT, ReminderState.FAILED):
            summary.skipped += 1
            return

        # 重试间隔限制（需求 4.7）：距上次尝试不足 60 秒则跳过本轮。
        if item.last_attempt_at is not None and (now - item.last_attempt_at) < MIN_RETRY_INTERVAL:
            summary.skipped += 1
            return

        payload = build_payload(record.name, record.expiration_date, now.date(), kind=kind)

        # 通过每个已启用渠道各发送一次（需求 4.6）。
        channels = self._enabled_channels()
        all_ok = True
        for ch in channels:
            result = ch.send(payload)
            if not result.ok:
                all_ok = False

        item.last_attempt_at = now
        if channels and all_ok:
            item.state = ReminderState.SENT
            summary.sent += 1
        else:
            item.retry_count += 1
            if item.retry_count >= MAX_RETRIES:
                item.state = ReminderState.FAILED  # 终态（需求 3.5）
            else:
                item.state = ReminderState.PENDING
            summary.failed += 1

        self._store.mark_reminder_sent(item)
