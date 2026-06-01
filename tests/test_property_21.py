# Feature: domain-manager, Property 21: 列表渲染包含必要字段
"""Property 21: 列表渲染包含必要字段。

对任意域名记录集合，列表渲染输出中每条记录都包含其域名名称、Expiration_Date、
剩余天数（整数天）与 Domain_Status。

Validates: Requirements 8.1
"""
from datetime import date, datetime, timedelta

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from domain_manager.domain_service import DomainInput
from tests.web_helpers import login, make_app

_FIXED = datetime(2026, 6, 1, 12, 0, 0)


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(
    offsets=st.lists(st.integers(min_value=-30, max_value=120), min_size=1, max_size=5),
)
def test_list_renders_required_fields(tmp_path_factory, offsets):
    d = tmp_path_factory.mktemp("p21")
    app = make_app(d, clock=lambda: _FIXED)
    service = app.config["DOMAIN_SERVICE"]

    expected = []
    for i, off in enumerate(offsets):
        name = f"d{i}.example.com"
        exp = (_FIXED.date() + timedelta(days=off))
        service.create_domain(DomainInput(name=name, expiration_date=exp.isoformat()))
        expected.append((name, exp, off))

    client = app.test_client()
    login(client)
    resp = client.get("/domains")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    for name, exp, off in expected:
        assert name in html                      # 域名名称
        assert exp.isoformat() in html           # 到期时间
        assert str(off) in html                  # 剩余天数（整数天）
    # 状态值出现在页面中。
    assert ("Active" in html or "Expiring" in html or "Expired" in html)
