# Feature: domain-manager, Property 19: 写入失败时内存记录不变
"""Property 19: 写入失败时内存记录不变。

对任意写操作，当底层持久化写入失败（磁盘满、无权限、IO 错误）时，操作返回写入失败错误，
且内存中的记录集合保持不变。

Validates: Requirements 6.5
"""
import os
from datetime import date

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.domain_service import DomainInput, DomainService
from domain_manager.models import ErrorCode, Result
from domain_manager.store import DataStore
from tests.strategies import valid_dates, valid_domain_names

_FIXED_TODAY = date(2026, 6, 1)


class FailingStore(DataStore):
    """所有写操作均返回 STORE_WRITE_FAILED 的存储（模拟磁盘/IO 故障）。"""

    fail_writes = False

    def _write(self, sql, params):
        if self.fail_writes:
            return Result.fail(ErrorCode.STORE_WRITE_FAILED, "模拟写入失败")
        return super()._write(sql, params)


@settings(max_examples=100, deadline=None)
@given(
    seed=st.lists(
        st.tuples(valid_domain_names(), valid_dates),
        min_size=0,
        max_size=5,
        unique_by=lambda t: t[0],
    ),
    new_name=valid_domain_names(),
    new_exp=valid_dates,
)
def test_write_failure_keeps_memory_unchanged(tmp_path_factory, seed, new_name, new_exp):
    d = tmp_path_factory.mktemp("p19")
    store = FailingStore(os.path.join(str(d), "p19.db"))
    clock = lambda: _FIXED_TODAY
    service = DomainService(store, clock=clock)
    service.load()

    # 正常写入种子数据。
    for name, exp in seed:
        if name == new_name:
            continue
        service.create_domain(DomainInput(name=name, expiration_date=exp.isoformat()))

    before = {r.id: (r.name, r.expiration_date) for r in service.records_snapshot}

    # 开启写失败，尝试创建新记录。
    store.fail_writes = True
    res = service.create_domain(DomainInput(name=new_name, expiration_date=new_exp.isoformat()))
    assert res.is_err
    assert res.error.code == ErrorCode.STORE_WRITE_FAILED

    after = {r.id: (r.name, r.expiration_date) for r in service.records_snapshot}
    assert after == before

    # 删除已有记录在写失败时也应保持内存不变。
    if before:
        some_id = next(iter(before))
        del_res = service.delete_domain(some_id)
        assert del_res.is_err
        assert del_res.error.code == ErrorCode.STORE_WRITE_FAILED
        after2 = {r.id: (r.name, r.expiration_date) for r in service.records_snapshot}
        assert after2 == before
