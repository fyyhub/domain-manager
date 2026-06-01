# Feature: domain-manager, Property 14: 多渠道各发送一次
"""Property 14: 多渠道各发送一次。

对任意已启用的 Notification_Channel 集合，触发一条提醒时每个已启用渠道恰好被调用一次发送。

Validates: Requirements 4.6
"""
from datetime import date, datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.reminder_helpers import CountingChannel, build_reminder_service

_NOW = datetime(2026, 6, 1, 9, 0, 0)


@settings(max_examples=60, deadline=None)
@given(
    n_enabled=st.integers(min_value=1, max_value=4),
    n_disabled=st.integers(min_value=0, max_value=3),
)
def test_multi_channel_each_once(tmp_path_factory, n_enabled, n_disabled):
    d = tmp_path_factory.mktemp("p14")
    # 单个临近到期域名，触发一档提醒。
    domains = [("d0.example.com", date(2026, 6, 3))]
    thresholds = [7]

    enabled = [CountingChannel(name=f"en{i}", enabled=True, succeed=True) for i in range(n_enabled)]
    disabled = [CountingChannel(name=f"dis{i}", enabled=False, succeed=True) for i in range(n_disabled)]
    channels = enabled + disabled

    reminder, _, _ = build_reminder_service(d, domains, thresholds, channels, lambda: _NOW)
    reminder.run_reminder_check(now=_NOW)

    # 每个已启用渠道恰好发送一次。
    for ch in enabled:
        assert len(ch.sent) == 1
    # 未启用渠道不发送。
    for ch in disabled:
        assert len(ch.sent) == 0
