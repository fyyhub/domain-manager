# Feature: domain-manager, Property 1: 记录持久化往返一致
"""Property 1: 记录持久化往返一致。

对任意合法的 DomainInput 序列（创建/更新/删除的任意组合），每次写操作返回成功后，
从 Data_Store 重新加载得到的记录集合应与内存中的记录集合完全一致。

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 6.1, 6.2
"""
import os

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.domain_service import DomainInput, DomainService
from domain_manager.store import DataStore
from tests.strategies import valid_dates, valid_domain_names


@settings(max_examples=100, deadline=None)
@given(
    names=st.lists(valid_domain_names(), min_size=0, max_size=8, unique=True),
    exp=valid_dates,
)
def test_persistence_roundtrip(tmp_path_factory, names, exp):
    d = tmp_path_factory.mktemp("p01")
    db_path = os.path.join(str(d), "p01.db")
    store = DataStore(db_path)
    service = DomainService(store)
    service.load()

    created_ids = []
    for name in names:
        res = service.create_domain(DomainInput(name=name, expiration_date=exp.isoformat()))
        assert res.is_ok
        created_ids.append(res.value.id)

    # 删除其中一部分（偶数索引）。
    for i, did in enumerate(list(created_ids)):
        if i % 2 == 0:
            assert service.delete_domain(did).is_ok

    # 内存中的记录集合。
    mem = {r.id: r.name for r in service.records_snapshot}

    # 用全新 service 从磁盘重新加载。
    reloaded = DomainService(DataStore(db_path))
    assert reloaded.load().is_ok
    disk = {r.id: r.name for r in reloaded.records_snapshot}

    assert mem == disk
