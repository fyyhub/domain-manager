# Feature: domain-manager, Property 23: 列表按剩余天数升序排列
"""Property 23: 列表按剩余天数升序排列。

对任意域名记录集合，列表排序后的输出按剩余天数非递减排列，
且为输入集合的一个排列（不增删记录）。

Validates: Requirements 8.4
"""
import os
from datetime import date

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.domain_service import DomainInput, DomainService
from domain_manager.status import status_remaining_days
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
)
def test_sorted_ascending_by_remaining_days(tmp_path_factory, items):
    d = tmp_path_factory.mktemp("p23")
    clock = lambda: _FIXED_TODAY
    service = DomainService(DataStore(os.path.join(str(d), "p23.db")), clock=clock)
    service.load()
    for name, exp in items:
        service.create_domain(DomainInput(name=name, expiration_date=exp.isoformat()))

    listed = service.list_domains()

    # 是输入集合的一个排列（不增删）。
    assert len(listed) == len(items)
    assert {r.name for r in listed} == {name for name, _ in items}

    # 剩余天数非递减（None 视为正无穷，排最后）。
    def key(r):
        rd = status_remaining_days(r.expiration_date, _FIXED_TODAY)
        return float("inf") if rd is None else rd

    keys = [key(r) for r in listed]
    assert keys == sorted(keys)
