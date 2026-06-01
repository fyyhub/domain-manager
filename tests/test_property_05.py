# Feature: domain-manager, Property 5: 加载后的状态与到期时间一致
"""Property 5: 加载后的状态与到期时间一致。

对任意域名记录集合，持久化后重新加载，每条记录的 Domain_Status 等于对其到期时间
与当前日期重新计算 compute_status 的结果（状态始终为派生值）。

Validates: Requirements 2.2
"""
import os
from datetime import date

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.domain_service import DomainInput, DomainService
from domain_manager.status import compute_status
from domain_manager.store import DataStore
from tests.strategies import valid_dates, valid_domain_names

_FIXED_TODAY = date(2026, 6, 1)


@settings(max_examples=100, deadline=None)
@given(
    items=st.lists(
        st.tuples(valid_domain_names(), valid_dates),
        min_size=0,
        max_size=8,
        unique_by=lambda t: t[0],
    ),
    threshold=st.integers(min_value=1, max_value=365),
)
def test_loaded_status_consistent(tmp_path_factory, items, threshold):
    d = tmp_path_factory.mktemp("p05")
    db_path = os.path.join(str(d), "p05.db")
    clock = lambda: _FIXED_TODAY

    service = DomainService(DataStore(db_path), status_threshold=threshold, clock=clock)
    service.load()
    for name, exp in items:
        assert service.create_domain(
            DomainInput(name=name, expiration_date=exp.isoformat())
        ).is_ok

    # 用新 service 重新加载并断言每条状态都等于重算结果。
    reloaded = DomainService(DataStore(db_path), status_threshold=threshold, clock=clock)
    assert reloaded.load().is_ok
    for rec in reloaded.records_snapshot:
        expected = compute_status(rec.expiration_date, _FIXED_TODAY, threshold)
        assert rec.status == expected
