"""Domain_Manager 核心服务（DomainService）。

对应 design.md Components and Interfaces 的 DomainService 与需求 1、2、8.3、8.4。

职责：
- 域名记录 CRUD，含名称/到期时间校验、重复检测、不存在处理。
- 写操作在返回成功前经 Data_Store 持久化（需求 6.1）；写失败时内存不变（需求 6.5）。
- 列表查询时重算状态、按状态筛选、按剩余天数升序排序、空库返回空列表。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, List, Optional

from .models import (
    DomainRecord,
    DomainStatus,
    ErrorCode,
    Result,
    Source,
)
from .status import compute_status, status_remaining_days
from .store import DataStore
from .validation import is_valid_domain_name, is_valid_expiration_date, parse_date


@dataclass
class DomainInput:
    """创建/更新域名的输入。"""

    name: str
    expiration_date: object = None  # str | date | None
    platform: str = ""
    notes: str = ""
    source: Source = Source.MANUAL
    registered_date: object = None


class DomainService:
    """域名核心服务。内存中维护记录集合，并与 Data_Store 同步。"""

    def __init__(
        self,
        store: DataStore,
        status_threshold: int = 30,
        clock: Optional[Callable[[], date]] = None,
    ):
        self._store = store
        self._status_threshold = status_threshold
        # clock 可注入，便于测试确定性（默认取系统本地今天）。
        self._clock = clock or (lambda: datetime.now().date())
        self._records: dict = {}  # id -> DomainRecord

    # ----------------------------------------------------------------- #
    # 加载
    # ----------------------------------------------------------------- #
    def load(self) -> Result:
        """从 Data_Store 加载全部记录并重算状态（需求 2.2/6.2）。"""
        result = self._store.load_all_domains()
        if result.is_err:
            return result
        today = self._clock()
        self._records = {}
        for rec in result.value:
            rec.status = compute_status(rec.expiration_date, today, self._status_threshold)
            self._records[rec.id] = rec
        return Result.ok(list(self._records.values()))

    def set_status_threshold(self, value: int) -> None:
        """更新状态计算阈值（由 Config_Service 在配置变更后调用）。"""
        self._status_threshold = value

    # ----------------------------------------------------------------- #
    # CRUD
    # ----------------------------------------------------------------- #
    def create_domain(self, data: DomainInput) -> Result:
        """创建域名记录（需求 1.1/1.5/1.6/1.7/6.1）。"""
        # 名称格式校验（需求 1.6）
        if not is_valid_domain_name(data.name):
            return Result.fail(ErrorCode.INVALID_NAME, "域名名称为空或不符合三级域名格式")
        # 到期时间校验（需求 1.7）
        if not is_valid_expiration_date(data.expiration_date):
            return Result.fail(ErrorCode.INVALID_DATE, "到期时间为空或不是合法日历日期")
        # 重复检测（需求 1.5）
        if self._find_by_name(data.name) is not None:
            return Result.fail(ErrorCode.DUPLICATE, "域名名称已存在")

        now = datetime.now()
        record = DomainRecord(
            name=data.name,
            expiration_date=parse_date(data.expiration_date),
            platform=data.platform,
            source=data.source,
            registered_date=parse_date(data.registered_date),
            notes=data.notes,
            created_at=now,
            updated_at=now,
        )
        # 先持久化，成功后才更新内存（需求 6.1/6.5）。
        write = self._store.save_domain(record)
        if write.is_err:
            return write
        record.status = compute_status(
            record.expiration_date, self._clock(), self._status_threshold
        )
        self._records[record.id] = record
        return Result.ok(record)

    def get_domain(self, domain_id: str) -> Result:
        rec = self._records.get(domain_id)
        if rec is None:
            return Result.fail(ErrorCode.NOT_FOUND, "域名记录不存在")
        return Result.ok(rec)

    def update_domain(self, domain_id: str, data: DomainInput) -> Result:
        """更新域名记录（需求 1.3/1.6/1.7/1.8/6.1）。"""
        existing = self._records.get(domain_id)
        if existing is None:
            return Result.fail(ErrorCode.NOT_FOUND, "域名记录不存在")
        if not is_valid_domain_name(data.name):
            return Result.fail(ErrorCode.INVALID_NAME, "域名名称为空或不符合三级域名格式")
        if not is_valid_expiration_date(data.expiration_date):
            return Result.fail(ErrorCode.INVALID_DATE, "到期时间为空或不是合法日历日期")
        # 改名后若与其它记录重名则拒绝（需求 1.5）。
        clash = self._find_by_name(data.name)
        if clash is not None and clash.id != domain_id:
            return Result.fail(ErrorCode.DUPLICATE, "域名名称已存在")

        updated = DomainRecord(
            id=existing.id,
            name=data.name,
            expiration_date=parse_date(data.expiration_date),
            platform=data.platform,
            source=data.source,
            registered_date=parse_date(data.registered_date),
            notes=data.notes,
            created_at=existing.created_at,
            updated_at=datetime.now(),
        )
        write = self._store.update_domain(updated)
        if write.is_err:
            return write
        updated.status = compute_status(
            updated.expiration_date, self._clock(), self._status_threshold
        )
        self._records[domain_id] = updated
        return Result.ok(updated)

    def delete_domain(self, domain_id: str) -> Result:
        """删除域名记录（需求 1.4/1.8/6.1）。"""
        if domain_id not in self._records:
            return Result.fail(ErrorCode.NOT_FOUND, "域名记录不存在")
        write = self._store.delete_domain(domain_id)
        if write.is_err:
            return write
        del self._records[domain_id]
        return Result.ok(None)

    # ----------------------------------------------------------------- #
    # Cloudflare 同步专用（需求 5.2/5.3）
    # ----------------------------------------------------------------- #
    def create_domain_from_sync(self, data: DomainInput) -> Result:
        """从 Cloudflare 同步创建记录。

        与 create_domain 不同：允许 Expiration_Date 为空（Cloudflare 不提供到期时间，
        需求 5.2/2.9），但仍校验域名格式与名称唯一性。
        """
        if not is_valid_domain_name(data.name):
            return Result.fail(ErrorCode.INVALID_NAME, "域名名称不符合三级域名格式")
        if self._find_by_name(data.name) is not None:
            return Result.fail(ErrorCode.DUPLICATE, "域名名称已存在")
        now = datetime.now()
        record = DomainRecord(
            name=data.name,
            expiration_date=parse_date(data.expiration_date),
            platform=data.platform or "Cloudflare",
            source=Source.CLOUDFLARE,
            registered_date=parse_date(data.registered_date),
            notes=data.notes,
            created_at=now,
            updated_at=now,
        )
        write = self._store.save_domain(record)
        if write.is_err:
            return write
        record.status = compute_status(
            record.expiration_date, self._clock(), self._status_threshold
        )
        self._records[record.id] = record
        return Result.ok(record)

    def update_domain_from_sync(self, domain_id: str, data: DomainInput) -> Result:
        """从 Cloudflare 同步更新记录的 Cloudflare 字段，保留手动录入的到期时间。

        与 update_domain 不同：不强制 Expiration_Date 非空（需求 5.3 要求保留原值，
        而原值可能为空）。
        """
        existing = self._records.get(domain_id)
        if existing is None:
            return Result.fail(ErrorCode.NOT_FOUND, "域名记录不存在")
        if not is_valid_domain_name(data.name):
            return Result.fail(ErrorCode.INVALID_NAME, "域名名称不符合三级域名格式")
        updated = DomainRecord(
            id=existing.id,
            name=data.name,
            expiration_date=parse_date(data.expiration_date),
            platform=data.platform,
            source=data.source,
            registered_date=parse_date(data.registered_date),
            notes=data.notes,
            created_at=existing.created_at,
            updated_at=datetime.now(),
        )
        write = self._store.update_domain(updated)
        if write.is_err:
            return write
        updated.status = compute_status(
            updated.expiration_date, self._clock(), self._status_threshold
        )
        self._records[domain_id] = updated
        return Result.ok(updated)

    # ----------------------------------------------------------------- #
    # 查询、筛选、排序
    # ----------------------------------------------------------------- #
    def list_domains(
        self,
        status_filter: Optional[DomainStatus] = None,
        recompute: bool = True,
    ) -> List[DomainRecord]:
        """列出域名记录（需求 1.2/1.9/2.2/8.3/8.4）。

        - recompute：以当前日期重算每条状态（默认开启）。
        - status_filter：仅返回该状态记录（需求 8.3）。
        - 始终按剩余天数升序排序，到期时间缺失（None）排在最后（需求 8.4）。
        - 空库返回空列表（需求 1.9）。
        """
        today = self._clock()
        records = list(self._records.values())
        if recompute:
            for rec in records:
                rec.status = compute_status(
                    rec.expiration_date, today, self._status_threshold
                )
        if status_filter is not None:
            records = [r for r in records if r.status == status_filter]

        def sort_key(r: DomainRecord):
            d = status_remaining_days(r.expiration_date, today)
            # None（到期缺失）排到最后。
            return (d is None, d if d is not None else 0)

        records.sort(key=sort_key)
        return records

    # ----------------------------------------------------------------- #
    # 内部
    # ----------------------------------------------------------------- #
    def _find_by_name(self, name: str) -> Optional[DomainRecord]:
        for rec in self._records.values():
            if rec.name == name:
                return rec
        return None

    @property
    def records_snapshot(self) -> List[DomainRecord]:
        """内存中记录的快照副本（用于属性测试断言内存不变）。"""
        return list(self._records.values())
