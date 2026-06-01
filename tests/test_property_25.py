# Feature: domain-manager, Property 25: 受保护资源需有效会话
"""Property 25: 受保护资源需有效会话。

对任意受保护路由，使用无会话或无效（含已超时、已登出）会话的请求都不会返回受保护内容，
而是被引导至登录页。

Validates: Requirements 9.1, 9.2
"""
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.web_helpers import make_app

_PROTECTED = ["/", "/domains", "/domains/new", "/config"]


@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(path=st.sampled_from(_PROTECTED))
def test_protected_requires_session(tmp_path_factory, path):
    d = tmp_path_factory.mktemp("p25")
    app = make_app(d)
    client = app.test_client()

    # 无会话访问受保护资源：应重定向到登录页（302 -> /login）。
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers.get("Location", "")


@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(fake_sid=st.text(min_size=1, max_size=40))
def test_invalid_session_rejected(tmp_path_factory, fake_sid):
    d = tmp_path_factory.mktemp("p25b")
    app = make_app(d)
    client = app.test_client()
    # 注入一个伪造的会话 id。
    with client.session_transaction() as sess:
        sess["dm_session_id"] = fake_sid
    resp = client.get("/domains", follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers.get("Location", "")
