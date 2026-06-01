# Feature: domain-manager, Property 28: 会话空闲超时判定正确
"""Property 28: 会话空闲超时判定正确。

对任意最后活动时间 last_active 与当前时间 now，validate_session 当且仅当
now − last_active 超过 30 分钟时判定会话失效；未超过时会话有效并刷新最后活动时间。

Validates: Requirements 9.5
"""
from datetime import datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.auth import SESSION_IDLE_TIMEOUT
from tests.test_auth_helpers import make_auth

# 秒级间隔，覆盖 30 分钟边界两侧。
_idle_seconds = st.integers(min_value=0, max_value=3600)
_CORRECT = "pw"


@settings(max_examples=100, deadline=None)
@given(idle_seconds=_idle_seconds)
def test_idle_timeout(tmp_path_factory, idle_seconds):
    d = tmp_path_factory.mktemp("p28")
    svc = make_auth(d, password=_CORRECT)
    base = datetime(2026, 6, 1, 12, 0, 0)

    session = svc.login("admin", _CORRECT, now=base).value
    later = base + timedelta(seconds=idle_seconds)

    result = svc.validate_session(session.session_id, now=later)
    if timedelta(seconds=idle_seconds) > SESSION_IDLE_TIMEOUT:
        assert result.is_err
    else:
        assert result.is_ok
        # 校验成功后刷新最后活动时间为 now。
        assert result.value.last_active_at == later
