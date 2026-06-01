# Feature: domain-manager, Property 15: 同步保留手动到期时间并正确合并
"""Property 15: 同步保留手动到期时间并正确合并。

对任意库存记录集合（含用户手动录入的 Expiration_Date）与 Cloudflare 拉取的域名集合，
同步合并后：仅存在于 Cloudflare 的域名被新建且来源标记为 Cloudflare；两侧都存在的域名
其来自 Cloudflare 的字段被更新，但其手动录入的 Expiration_Date 保持不变。

Validates: Requirements 5.2, 5.3
"""
from datetime import date

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.models import Source
from tests.cloudflare_helpers import FakeClient, build_sync
from tests.strategies import valid_dates, valid_domain_names


@settings(max_examples=80, deadline=None)
@given(
    existing=st.lists(
        st.tuples(valid_domain_names(), valid_dates),
        min_size=0,
        max_size=6,
        unique_by=lambda t: t[0],
    ),
    cf_only=st.lists(valid_domain_names(), min_size=0, max_size=6, unique=True),
)
def test_sync_preserves_manual_expiration(tmp_path_factory, existing, cf_only):
    d = tmp_path_factory.mktemp("p15")
    existing_names = {n for n, _ in existing}
    # cf_names = 库存中的一半（模拟两侧都有）+ cf_only（仅 Cloudflare）。
    overlap = [n for n, _ in existing]
    cf_names = list({*overlap, *[n for n in cf_only if n not in existing_names]})

    sync, domain_service = build_sync(d, existing, FakeClient(cf_names))

    # 记录同步前每个库存域名的手动到期时间。
    before_exp = {r.name: r.expiration_date for r in domain_service.list_domains()}

    result = sync.sync()
    assert result.is_ok

    after = {r.name: r for r in domain_service.list_domains()}

    # 两侧都存在的域名：手动到期时间保持不变。
    for name in overlap:
        assert after[name].expiration_date == before_exp[name]
        assert after[name].source == Source.CLOUDFLARE

    # 仅 Cloudflare 的域名：被新建，来源为 Cloudflare。
    for name in cf_names:
        if name not in existing_names:
            assert name in after
            assert after[name].source == Source.CLOUDFLARE
