# Feature: domain-manager, Property 10: 提醒重试状态机不变量
"""Property 10: 提醒重试状态机不变量。

对任意持续失败的发送序列，单条提醒的 retry_count 永不超过 3；达到 3 次后进入 Failed
终态并不再被重试；未达终态时保持 Pending 并在后续周期重发，且相邻两次发送尝试的时间
间隔判定不小于 60 秒。

Validates: Requirements 3.5, 4.7, 4.8
"""
from datetime import date, datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.models import ReminderState
from domain_manager.reminders import MAX_RETRIES, MIN_RETRY_INTERVAL
from tests.reminder_helpers import CountingChannel, build_reminder_service

_START = datetime(2026, 6, 1, 9, 0, 0)


@settings(max_examples=60, deadline=None)
@given(
    # 各轮之间的间隔秒数（>=60 以确保重试被允许）。
    gaps=st.lists(st.integers(min_value=60, max_value=600), min_size=5, max_size=8),
)
def test_retry_state_machine(tmp_path_factory, gaps):
    d = tmp_path_factory.mktemp("p10")
    # 一个临近到期的域名，必然触发某档提醒。
    domains = [("d0.example.com", date(2026, 6, 2))]
    thresholds = [7]
    channel = CountingChannel(succeed=False)  # 持续失败

    state = {"now": _START}
    clock = lambda: state["now"]
    reminder, store, _ = build_reminder_service(d, domains, thresholds, [channel], clock)

    # 多轮检查，每轮推进时间。
    now = _START
    for gap in gaps:
        reminder.run_reminder_check(now=now)
        now = now + timedelta(seconds=gap)

    # 检查存储中该提醒的最终状态。
    items = store.load_reminder_sent().value
    assert len(items) >= 1
    for item in items:
        # retry_count 永不超过 3。
        assert item.retry_count <= MAX_RETRIES
        # 达到上限即 Failed 终态。
        if item.retry_count >= MAX_RETRIES:
            assert item.state == ReminderState.FAILED


@settings(max_examples=40, deadline=None)
@given(gap_seconds=st.integers(min_value=0, max_value=59))
def test_retry_respects_min_interval(tmp_path_factory, gap_seconds):
    """相邻尝试间隔 < 60 秒时不重试（需求 4.7）。"""
    d = tmp_path_factory.mktemp("p10b")
    domains = [("d0.example.com", date(2026, 6, 2))]
    thresholds = [7]
    channel = CountingChannel(succeed=False)

    now = _START
    reminder, store, _ = build_reminder_service(
        d, domains, thresholds, [channel], lambda: now
    )

    reminder.run_reminder_check(now=now)
    sent_after_first = len(channel.sent)

    # 间隔不足 60 秒再次运行，不应再次尝试发送。
    later = now + timedelta(seconds=gap_seconds)
    reminder.run_reminder_check(now=later)
    assert len(channel.sent) == sent_after_first
