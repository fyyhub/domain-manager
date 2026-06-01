"""Web 界面集成测试（任务 13.7，需求 8.2/8.8、9）。

验证登录流程、CRUD、错误时展示可读提示并保留输入、受保护路由无认证不泄露数据、
配置页不回显凭证明文。
"""
from datetime import datetime

from tests.web_helpers import TEST_PASSWORD, login, make_app

_FIXED = datetime(2026, 6, 1, 12, 0, 0)


def _app(tmp_path):
    return make_app(tmp_path, clock=lambda: _FIXED)


def test_login_and_logout_flow(tmp_path):
    app = _app(tmp_path)
    client = app.test_client()

    # 错误密码：停留在登录，提示统一文案。
    bad = client.post(
        "/login", data={"username": "admin", "password": "wrong"}, follow_redirects=True
    )
    assert "用户名或密码错误" in bad.get_data(as_text=True)

    # 正确登录后可访问受保护页面。
    login(client)
    resp = client.get("/domains")
    assert resp.status_code == 200

    # 登出后再访问被重定向到登录。
    client.post("/logout")
    resp2 = client.get("/domains", follow_redirects=False)
    assert resp2.status_code in (301, 302)
    assert "/login" in resp2.headers.get("Location", "")


def test_create_domain_via_web(tmp_path):
    app = _app(tmp_path)
    client = app.test_client()
    login(client)

    resp = client.post(
        "/domains",
        data={
            "name": "sub.example.com",
            "expiration_date": "2030-01-01",
            "platform": "Cloudflare",
            "notes": "test",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "sub.example.com" in resp.get_data(as_text=True)


def test_create_invalid_domain_shows_error_and_keeps_input(tmp_path):
    app = _app(tmp_path)
    client = app.test_client()
    login(client)

    resp = client.post(
        "/domains",
        data={
            "name": "not-a-valid-domain",  # 非三级域名
            "expiration_date": "2030-01-01",
            "platform": "X",
            "notes": "keep me",
        },
    )
    # 返回 400，展示可读错误，且保留用户已输入的数据（需求 8.8）。
    assert resp.status_code == 400
    html = resp.get_data(as_text=True)
    assert "格式" in html or "三级域名" in html
    assert "not-a-valid-domain" in html  # 输入被保留
    assert "keep me" in html


def test_protected_routes_no_data_leak_without_auth(tmp_path):
    app = _app(tmp_path)
    # 预置一条域名。
    app.config["DOMAIN_SERVICE"].create_domain(
        __import__("domain_manager.domain_service", fromlist=["DomainInput"]).DomainInput(
            name="secret.example.com", expiration_date="2030-01-01"
        )
    )
    client = app.test_client()
    resp = client.get("/domains", follow_redirects=False)
    # 未认证：重定向，且响应体不含域名数据。
    assert resp.status_code in (301, 302)
    assert "secret.example.com" not in resp.get_data(as_text=True)


def test_config_page_does_not_reveal_cloudflare_plaintext(tmp_path):
    app = _app(tmp_path)
    client = app.test_client()
    login(client)

    secret_token = "cf-super-secret-token-XYZ"
    client.post(
        "/config",
        data={"section": "cloudflare", "cloudflare_token": secret_token},
        follow_redirects=True,
    )
    resp = client.get("/config")
    html = resp.get_data(as_text=True)
    # 明文绝不出现在配置页（需求 8.6）。
    assert secret_token not in html
    # 显示掩码。
    assert "••••" in html


def test_cloudflare_sync_summary_displayed(tmp_path):
    app = _app(tmp_path)

    # 注入一个假的 CloudflareSync，返回固定摘要。
    from domain_manager.cloudflare import SyncSummary
    from domain_manager.models import Result

    class FakeSync:
        def sync(self):
            return Result.ok(SyncSummary(created=2, updated=3))

    app.config["CLOUDFLARE_SYNC"] = FakeSync()

    client = app.test_client()
    login(client)
    resp = client.post("/cloudflare/sync", follow_redirects=True)
    html = resp.get_data(as_text=True)
    assert "新建 2" in html and "更新 3" in html
