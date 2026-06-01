# Feature: domain-manager, Property 9: 提醒发送去重幂等
"""Property 9: 提醒发送去重幂等。

对任意域名记录与阈值集合，运行一次提醒检查并将成功发送的 (域名, 阈值) 标记为已发送后，
再次运行检查不会对同一 (域名, 阈值) 组合再次产生发送；过期提醒在已发送后也不会
对同一域名再次产生发送。

Validates: Requirements 3.3, 3.4
"""
from datetime import date, datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.reminder_helpers import CountingChannel, build_reminder_service

_NOW = datetime(2026, 6, 1, 9, 0, 0)


@settings(max_examples=80, deadline=None)
@given(
    offsets=st.lists(
        st.integers(min_value=-10, max_value=60), min_size=1, max_size=5
    ),
    thresholds=st.lists(
        st.integers(min_value=1, max_value=30), min_size=1, max_size=4, unique=True
    ),
)
def test_reminder_dedup_idempotent(tmp_path_factory, offsets, thresholds):
    d = tmp_path_factory.mktemp("p09")
    domains = [
        (f"d{i}.example.com", date(2026, 6, 1) + timedelta(days=off))
        for i, off in enumerate(offsets)
    ]
    channel = CountingChannel(succeed=True)
    clock = lambda: _NOW
    reminder, _, _ = build_reminder_service(d, domains, thresholds, [channel], clock)

    # 第一次运行：发送若干提醒。
    reminder.run_reminder_check(now=_NOW)
    first_count = len(channel.sent)

    # 第二次运行（同一天）：不应再产生任何发送。
    reminder.run_reminder_check(now=_NOW)
    second_count = len(channel.sent)

    assert second_count == first_count
