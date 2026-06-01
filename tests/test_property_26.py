# Feature: domain-manager, Property 26: 正确凭据建立有效会话
"""Property 26: 正确凭据建立有效会话。

对任意已注册账户，使用正确口令登录都会建立一个会话，且该会话在自最后活动起
30 分钟的空闲时间内对受保护资源有效。

Validates: Requirements 9.3
"""
from datetime import datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.test_auth_helpers import make_auth

_passwords = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=40
)
# 0–29 分钟内的空闲间隔（严格小于 30 分钟）。
_idle_minutes = st.integers(min_value=0, max_value=29)


@settings(max_examples=100, deadline=None)
@given(password=_passwords, idle=_idle_minutes)
def test_valid_login_creates_valid_session(tmp_path_factory, password, idle):
    d = tmp_path_factory.mktemp("p26")
    base = datetime(2026, 6, 1, 12, 0, 0)
    svc = make_auth(d, password=password)

    res = svc.login("admin", password, now=base)
    assert res.is_ok
    session = res.value
    assert session.session_id

    # 在 30 分钟空闲窗口内校验仍然有效。
    later = base + timedelta(minutes=idle)
    check = svc.validate_session(session.session_id, now=later)
    assert check.is_ok
