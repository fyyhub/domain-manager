# Feature: domain-manager, Property 22: 按状态筛选只返回该状态记录
"""Property 22: 按状态筛选只返回该状态记录。

对任意域名记录集合与所选 Domain_Status，筛选结果中的所有记录状态都等于所选状态，
且原集合中所有该状态记录都出现在结果中。

Validates: Requirements 8.3
"""
import os
from datetime import date

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.domain_service import DomainInput, DomainService
from domain_manager.models import DomainStatus
from domain_manager.store import DataStore
from tests.strategies import valid_dates, valid_domain_names

_FIXED_TODAY = date(2026, 6, 1)


@settings(max_examples=100, deadline=None)
@given(
    items=st.lists(
        st.tuples(valid_domain_names(), valid_dates),
        min_size=0,
        max_size=10,
        unique_by=lambda t: t[0],
    ),
    status=st.sampled_from(list(DomainStatus)),
    threshold=st.integers(min_value=1, max_value=365),
)
def test_status_filter(tmp_path_factory, items, status, threshold):
    d = tmp_path_factory.mktemp("p22")
    clock = lambda: _FIXED_TODAY
    service = DomainService(
        DataStore(os.path.join(str(d), "p22.db")), status_threshold=threshold, clock=clock
    )
    service.load()
    for name, exp in items:
        service.create_domain(DomainInput(name=name, expiration_date=exp.isoformat()))

    filtered = service.list_domains(status_filter=status)
    all_recs = service.list_domains()

    # 结果中每条都等于所选状态。
    assert all(r.status == status for r in filtered)
    # 原集合中所有该状态记录都出现在结果中。
    expected_ids = {r.id for r in all_recs if r.status == status}
    assert {r.id for r in filtered} == expected_ids
