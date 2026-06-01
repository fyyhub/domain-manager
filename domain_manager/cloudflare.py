"""Cloudflare_Sync：可选的 Cloudflare DNS 同步（需求 5）。

通过 Cloudflare API v4 拉取 DNS 区域与记录，合并到 Data_Store：
- 仅存在于 Cloudflare 的域名 -> 新建，来源标记 Cloudflare（需求 5.2）。
- 两侧都存在的域名 -> 更新来自 Cloudflare 的字段，但保留用户手动录入的
  Expiration_Date 不变（需求 5.3）。
- 凭证无效 -> 停止同步、数据不变、返回错误（需求 5.4）。
- 网络失败 -> 最多重试 3 次，全部失败后数据不变、返回错误（需求 5.5）。
- 成功 -> 返回新建/更新数量摘要（需求 5.6）。
- 同步进行中再次发起 -> 拒绝（需求 5.7）。

为便于测试，Cloudflare API 访问通过可注入的 client 抽象，默认实现使用 requests。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, List, Optional

from .domain_service import DomainInput, DomainService
from .models import ErrorCode, Result, Source

# 单次 Cloudflare API 请求超时（需求 5.1）。
REQUEST_TIMEOUT_SECONDS = 30
# 网络失败最大重试次数（需求 5.5）。
MAX_NETWORK_RETRIES = 3

API_BASE = "https://api.cloudflare.com/client/v4"


@dataclass
class SyncSummary:
    """同步结果摘要（需求 5.6）。"""

    created: int = 0
    updated: int = 0


class CloudflareError(Exception):
    """Cloudflare 客户端错误基类。"""


class InvalidCredentialsError(CloudflareError):
    """凭证无效/被拒绝（需求 5.4）。"""


class NetworkError(CloudflareError):
    """网络层失败（需求 5.5）。"""


class CloudflareClient:
    """Cloudflare API 客户端（默认实现，使用 requests）。

    fetch_domains() 返回 Cloudflare 上的域名名称列表。
    """

    def __init__(self, token: str, session=None):
        self._token = token
        self._session = session

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def fetch_domains(self) -> List[str]:
        import requests

        session = self._session or requests
        names = set()
        try:
            zones_resp = session.get(
                f"{API_BASE}/zones",
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.exceptions.RequestException as exc:
            raise NetworkError(str(exc)) from exc

        if zones_resp.status_code in (401, 403):
            raise InvalidCredentialsError("Cloudflare 凭证无效或被拒绝")
        if zones_resp.status_code >= 500:
            raise NetworkError(f"Cloudflare 服务端错误：{zones_resp.status_code}")

        zones = zones_resp.json().get("result", [])
        for zone in zones:
            zone_id = zone.get("id")
            try:
                rec_resp = session.get(
                    f"{API_BASE}/zones/{zone_id}/dns_records",
                    headers=self._headers(),
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
            except requests.exceptions.RequestException as exc:
                raise NetworkError(str(exc)) from exc
            if rec_resp.status_code in (401, 403):
                raise InvalidCredentialsError("Cloudflare 凭证无效或被拒绝")
            for rec in rec_resp.json().get("result", []):
                name = rec.get("name")
                if name:
                    names.add(name)
        return sorted(names)


class CloudflareSync:
    """协调拉取、合并与并发控制。"""

    def __init__(
        self,
        domain_service: DomainService,
        client_factory: Callable[[], CloudflareClient],
    ):
        self._domain_service = domain_service
        self._client_factory = client_factory
        self._lock = threading.Lock()

    def sync(self) -> Result:
        """执行一次同步（需求 5）。"""
        # 互斥：进行中再次发起则拒绝（需求 5.7）。
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            return Result.fail(ErrorCode.SYNC_IN_PROGRESS, "已有同步正在进行")
        try:
            return self._do_sync()
        finally:
            self._lock.release()

    def _do_sync(self) -> Result:
        client = self._client_factory()

        # 拉取，带网络重试（需求 5.5）；凭证无效立即停止（需求 5.4）。
        last_err: Optional[Exception] = None
        cf_names = None
        for _ in range(MAX_NETWORK_RETRIES):
            try:
                cf_names = client.fetch_domains()
                break
            except InvalidCredentialsError as exc:
                return Result.fail(ErrorCode.CF_INVALID_CREDENTIALS, str(exc))
            except NetworkError as exc:
                last_err = exc
                continue
        if cf_names is None:
            # 重试全部失败，数据保持不变（需求 5.5）。
            return Result.fail(
                ErrorCode.CF_SYNC_FAILED, f"Cloudflare 同步失败：{last_err}"
            )

        # 合并（需求 5.2/5.3）。
        existing = {r.name: r for r in self._domain_service.list_domains()}
        summary = SyncSummary()
        for name in cf_names:
            if name in existing:
                rec = existing[name]
                # 更新来自 Cloudflare 的字段，但保留用户手动录入的 Expiration_Date。
                update = DomainInput(
                    name=rec.name,
                    expiration_date=rec.expiration_date,  # 保留不变（需求 5.3）
                    platform="Cloudflare",
                    notes=rec.notes,
                    source=Source.CLOUDFLARE,
                    registered_date=rec.registered_date,
                )
                res = self._domain_service.update_domain_from_sync(rec.id, update)
                if res.is_ok:
                    summary.updated += 1
            else:
                # Cloudflare 独有 -> 新建，来源标记 Cloudflare（需求 5.2）。
                # 到期时间未知（Cloudflare 不提供），由用户后续手动补充。
                create = DomainInput(
                    name=name,
                    expiration_date=None,
                    platform="Cloudflare",
                    source=Source.CLOUDFLARE,
                )
                res = self._domain_service.create_domain_from_sync(create)
                if res.is_ok:
                    summary.created += 1

        return Result.ok(summary)
