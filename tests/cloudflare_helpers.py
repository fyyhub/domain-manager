"""Cloudflare 同步测试辅助：可控的假客户端与服务装配。"""
import os
from datetime import date

from domain_manager.cloudflare import (
    CloudflareSync,
    InvalidCredentialsError,
    NetworkError,
)
from domain_manager.domain_service import DomainInput, DomainService
from domain_manager.store import DataStore


class FakeClient:
    """返回预设域名列表的假 Cloudflare 客户端，可模拟异常。"""

    def __init__(self, names, error=None, fail_times=0):
        self._names = names
        self._error = error          # "invalid" | "network" | None
        self._fail_times = fail_times  # 前 N 次抛 NetworkError
        self.calls = 0

    def fetch_domains(self):
        self.calls += 1
        if self._error == "invalid":
            raise InvalidCredentialsError("凭证无效")
        if self._error == "network":
            raise NetworkError("网络错误")
        if self.calls <= self._fail_times:
            raise NetworkError("瞬时网络错误")
        return list(self._names)


def build_sync(tmp_dir, existing, client):
    """装配 CloudflareSync。

    existing: list of (name, expiration_date|None) 预置到库中。
    client: 假客户端实例。
    """
    db_path = os.path.join(str(tmp_dir), "cf.db")
    store = DataStore(db_path)
    store.initialize()
    domain_service = DomainService(store, clock=lambda: date(2026, 6, 1))
    domain_service.load()
    for name, exp in existing:
        if exp is None:
            domain_service.create_domain_from_sync(DomainInput(name=name))
        else:
            domain_service.create_domain(
                DomainInput(name=name, expiration_date=exp.isoformat())
            )

    sync = CloudflareSync(domain_service, client_factory=lambda: client)
    return sync, domain_service
