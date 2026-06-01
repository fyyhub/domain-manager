# Feature: domain-manager, Property 29: 登出使会话立即失效
"""Property 29: 登出使会话立即失效。

对任意有效会话，执行登出后再用该会话校验都应失败，无法访问任何受保护资源。

Validates: Requirements 9.6
"""
from datetime import datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_auth_helpers import make_auth

_CORRECT = "pw"
_delays = st.integers(min_value=0, max_value=120)


@settings(max_examples=100, deadline=None)
@given(delay_seconds=_delays)
def test_logout_invalidates_session(tmp_path_factory, delay_seconds):
    d = tmp_path_factory.mktemp("p29")
    svc = make_auth(d, password=_CORRECT)
    base = datetime(2026, 6, 1, 12, 0, 0)

    session = svc.login("admin", _CORRECT, now=base).value
    # 登出前有效。
    assert svc.validate_session(session.session_id, now=base).is_ok

    svc.logout(session.session_id)

    # 登出后立即失效（即便在空闲超时窗口内）。
    later = base + timedelta(seconds=delay_seconds)
    assert svc.validate_session(session.session_id, now=later).is_err
