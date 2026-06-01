# Feature: domain-manager, Property 27: 认证失败提示不区分用户名与密码
"""Property 27: 认证失败提示不区分用户名与密码。

对任意错误用户名输入与错误口令输入，登录返回的认证失败提示文案完全相同
（不泄露是用户名错误还是密码错误）。

Validates: Requirements 9.4
"""
from datetime import datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.models import ErrorCode
from tests.test_auth_helpers import make_auth

_names = st.text(min_size=1, max_size=20)
_passwords = st.text(min_size=1, max_size=20)
_CORRECT = "correct-pass"


@settings(max_examples=100, deadline=None)
@given(wrong_user=_names, wrong_pass=_passwords)
def test_uniform_auth_failure_message(tmp_path_factory, wrong_user, wrong_pass):
    d = tmp_path_factory.mktemp("p27")
    svc = make_auth(d, username="admin", password=_CORRECT)

    base = datetime(2026, 6, 1, 12, 0, 0)
    # 用不同 now 避免触发锁定影响文案对比。
    msgs = []

    # 错误用户名 + 正确密码。
    if wrong_user != "admin":
        r1 = svc.login(wrong_user, _CORRECT, now=base)
        assert r1.is_err and r1.error.code == ErrorCode.AUTH_FAILED
        msgs.append(r1.error.message)

    # 正确用户名 + 错误密码。
    if wrong_pass != _CORRECT:
        r2 = svc.login("admin", wrong_pass, now=base + timedelta(seconds=1))
        assert r2.is_err and r2.error.code == ErrorCode.AUTH_FAILED
        msgs.append(r2.error.message)

    # 所有认证失败文案一致。
    assert len(set(msgs)) <= 1
