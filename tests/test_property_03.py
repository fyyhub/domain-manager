# Feature: domain-manager, Property 3: 无效域名名称与无效到期时间被拒绝
"""Property 3: 无效域名名称与无效到期时间被拒绝。

对任意无效域名名称或无效到期时间输入，create 都应返回相应的格式/日期无效错误，
且 Data_Store 保持不变。

Validates: Requirements 1.6, 1.7
"""
import os

from hypothesis import given, settings

from domain_manager.domain_service import DomainInput, DomainService
from domain_manager.models import ErrorCode
from domain_manager.store import DataStore
from tests.strategies import (
    invalid_dates,
    invalid_domain_names,
    valid_dates,
    valid_domain_names,
)


@settings(max_examples=100, deadline=None)
@given(bad_name=invalid_domain_names(), exp=valid_dates)
def test_invalid_name_rejected(tmp_path_factory, bad_name, exp):
    d = tmp_path_factory.mktemp("p03a")
    service = DomainService(DataStore(os.path.join(str(d), "p03a.db")))
    service.load()
    before = service.records_snapshot

    res = service.create_domain(DomainInput(name=bad_name, expiration_date=exp.isoformat()))
    assert res.is_err
    assert res.error.code == ErrorCode.INVALID_NAME
    assert service.records_snapshot == before


@settings(max_examples=100, deadline=None)
@given(name=valid_domain_names(), bad_date=invalid_dates())
def test_invalid_date_rejected(tmp_path_factory, name, bad_date):
    d = tmp_path_factory.mktemp("p03b")
    service = DomainService(DataStore(os.path.join(str(d), "p03b.db")))
    service.load()
    before = service.records_snapshot

    res = service.create_domain(DomainInput(name=name, expiration_date=bad_date))
    assert res.is_err
    assert res.error.code == ErrorCode.INVALID_DATE
    assert service.records_snapshot == before
