# Feature: domain-manager, Property 2: 重复域名与不存在记录的操作不改变存储
"""Property 2: 重复域名与不存在记录的操作不改变存储。

对任意已存在名称 X，再次以 X 创建都应被拒绝且存储不变；
对任意不在库中的 id，更新或删除都应返回 NOT_FOUND 且存储不变。

Validates: Requirements 1.5, 1.8
"""
import os

from hypothesis import given, settings

from domain_manager.domain_service import DomainInput, DomainService
from domain_manager.models import ErrorCode
from domain_manager.store import DataStore
from tests.strategies import valid_dates, valid_domain_names


@settings(max_examples=100, deadline=None)
@given(name=valid_domain_names(), exp=valid_dates)
def test_duplicate_and_not_found_unchanged(tmp_path_factory, name, exp):
    d = tmp_path_factory.mktemp("p02")
    db_path = os.path.join(str(d), "p02.db")
    service = DomainService(DataStore(db_path))
    service.load()

    first = service.create_domain(DomainInput(name=name, expiration_date=exp.isoformat()))
    assert first.is_ok
    snapshot = {r.id: r.name for r in service.records_snapshot}

    # 重复创建被拒绝，存储不变（需求 1.5）。
    dup = service.create_domain(DomainInput(name=name, expiration_date=exp.isoformat()))
    assert dup.is_err
    assert dup.error.code == ErrorCode.DUPLICATE
    assert {r.id: r.name for r in service.records_snapshot} == snapshot

    # 更新不存在记录被拒绝，存储不变（需求 1.8）。
    upd = service.update_domain(
        "nonexistent-id", DomainInput(name="x.y.z", expiration_date=exp.isoformat())
    )
    assert upd.is_err
    assert upd.error.code == ErrorCode.NOT_FOUND
    assert {r.id: r.name for r in service.records_snapshot} == snapshot

    # 删除不存在记录被拒绝，存储不变（需求 1.8）。
    dele = service.delete_domain("nonexistent-id")
    assert dele.is_err
    assert dele.error.code == ErrorCode.NOT_FOUND
    assert {r.id: r.name for r in service.records_snapshot} == snapshot

    # 磁盘上也保持一致。
    reloaded = DomainService(DataStore(db_path))
    reloaded.load()
    assert {r.id: r.name for r in reloaded.records_snapshot} == snapshot
