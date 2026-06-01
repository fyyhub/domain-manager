# Feature: domain-manager, Property 16: 同步摘要计数准确
"""Property 16: 同步摘要计数准确。

对任意库存集合与 Cloudflare 集合，同步结果摘要中的新建数等于实际被新建的记录数、
更新数等于实际被更新的记录数。

Validates: Requirements 5.6
"""
from hypothesis import given, settings
from hypothesis import strategies as st

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
    cf_extra=st.lists(valid_domain_names(), min_size=0, max_size=6, unique=True),
)
def test_sync_summary_counts(tmp_path_factory, existing, cf_extra):
    d = tmp_path_factory.mktemp("p16")
    existing_names = {n for n, _ in existing}

    # Cloudflare 返回：所有库存域名（将被更新）+ cf_extra 中的新域名（将被新建）。
    new_names = [n for n in cf_extra if n not in existing_names]
    cf_names = list(existing_names) + new_names

    sync, _ = build_sync(d, existing, FakeClient(cf_names))
    result = sync.sync()
    assert result.is_ok
    summary = result.value

    assert summary.created == len(set(new_names))
    assert summary.updated == len(existing_names)
