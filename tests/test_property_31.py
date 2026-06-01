# Feature: domain-manager, Property 31: 暴力破解锁定判定正确
"""Property 31: 暴力破解锁定判定正确。

对任意失败时间戳序列，当某账户在 15 分钟滑动窗口内的失败次数达到 5 次时，
is_locked 在随后的 15 分钟锁定期内为真，锁定期结束后为假。

Validates: Requirements 9.8
"""
from datetime import datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.auth import (
    LOCKOUT_DURATION,
    LOCKOUT_THRESHOLD,
    LOCKOUT_WINDOW,
)
from tests.test_auth_helpers import make_auth

_CORRECT = "correct-pass"
_base = datetime(2026, 6, 1, 12, 0, 0)


@settings(max_examples=100, deadline=None)
@given(
    # 5 次失败在 1 个 15 分钟窗口内的相对秒偏移（升序）。
    offsets=st.lists(
        st.integers(min_value=0, max_value=int(LOCKOUT_WINDOW.total_seconds()) - 1),
        min_size=LOCKOUT_THRESHOLD,
        max_size=LOCKOUT_THRESHOLD,
    ),
    probe_seconds=st.integers(min_value=0, max_value=int(LOCKOUT_DURATION.total_seconds()) * 2),
)
def test_lockout_window(tmp_path_factory, offsets, probe_seconds):
    d = tmp_path_factory.mktemp("p31")
    svc = make_auth(d, password=_CORRECT)

    offsets = sorted(offsets)
    # 连续 5 次错误密码，全部落在同一 15 分钟窗口内。
    for off in offsets:
        svc.login("admin", "wrong", now=_base + timedelta(seconds=off))

    last_fail = _base + timedelta(seconds=offsets[-1])
    # 触发锁定后，locked_until = last_fail + 锁定时长。
    locked_until = last_fail + LOCKOUT_DURATION

    probe = last_fail + timedelta(seconds=probe_seconds)
    locked = svc.is_locked("admin", now=probe)

    if probe < locked_until:
        assert locked is True
    else:
        assert locked is False
