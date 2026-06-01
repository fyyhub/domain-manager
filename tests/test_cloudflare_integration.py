"""Cloudflare 集成测试（任务 12.5，需求 5.1/5.4/5.5/5.7）。

使用 mock HTTP（requests 会话桩），验证 30 秒超时、网络异常重试 3 次、
凭证无效返回错误、并发同步互斥拒绝。
"""
import threading
import time
from datetime import date

import pytest

from domain_manager.cloudflare import (
    REQUEST_TIMEOUT_SECONDS,
    CloudflareClient,
    CloudflareSync,
    InvalidCredentialsError,
    NetworkError,
)
from domain_manager.domain_service import DomainService
from domain_manager.models import ErrorCode
from domain_manager.store import DataStore
from tests.cloudflare_helpers import FakeClient, build_sync


# --------------------------------------------------------------------------- #
# CloudflareClient 与 mock requests 会话
# --------------------------------------------------------------------------- #
class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeSession:
    """记录每次请求的 timeout 与 URL。"""

    def __init__(self, zones_status=200):
        self.calls = []
        self._zones_status = zones_status

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "timeout": timeout})
        if url.endswith("/zones"):
            if self._zones_status != 200:
                return _Resp(self._zones_status, {})
            return _Resp(200, {"result": [{"id": "zone1"}]})
        # dns_records
        return _Resp(
            200,
            {"result": [{"name": "a.b.com"}, {"name": "c.d.com"}]},
        )


def test_client_sets_30s_timeout_and_parses():
    session = _FakeSession()
    client = CloudflareClient("token", session=session)
    names = client.fetch_domains()
    assert set(names) == {"a.b.com", "c.d.com"}
    # 每次请求都设置了 30 秒超时。
    assert all(c["timeout"] == REQUEST_TIMEOUT_SECONDS for c in session.calls)


def test_client_invalid_credentials():
    session = _FakeSession(zones_status=403)
    client = CloudflareClient("bad-token", session=session)
    with pytest.raises(InvalidCredentialsError):
        client.fetch_domains()


# --------------------------------------------------------------------------- #
# CloudflareSync：重试、凭证、互斥
# --------------------------------------------------------------------------- #
def test_sync_retries_on_network_failure_then_succeeds(tmp_path_factory):
    d = tmp_path_factory.mktemp("cfretry")
    # 前 2 次抛 NetworkError，第 3 次成功。
    client = FakeClient(["a.b.com"], fail_times=2)
    sync, _ = build_sync(d, [], client)
    result = sync.sync()
    assert result.is_ok
    assert client.calls == 3  # 重试到第 3 次成功


def test_sync_fails_after_max_retries(tmp_path_factory):
    d = tmp_path_factory.mktemp("cffail")
    client = FakeClient([], error="network")
    sync, domain_service = build_sync(d, [("keep.me.com", date(2030, 1, 1))], client)
    before = {r.name for r in domain_service.list_domains()}

    result = sync.sync()
    assert result.is_err
    assert result.error.code == ErrorCode.CF_SYNC_FAILED
    # 数据保持不变。
    after = {r.name for r in domain_service.list_domains()}
    assert after == before


def test_sync_invalid_credentials_stops(tmp_path_factory):
    d = tmp_path_factory.mktemp("cfinvalid")
    client = FakeClient([], error="invalid")
    sync, domain_service = build_sync(d, [("keep.me.com", date(2030, 1, 1))], client)
    before = {r.name for r in domain_service.list_domains()}

    result = sync.sync()
    assert result.is_err
    assert result.error.code == ErrorCode.CF_INVALID_CREDENTIALS
    assert {r.name for r in domain_service.list_domains()} == before


def test_sync_mutex_rejects_concurrent(tmp_path_factory):
    """同步进行中再次发起被拒绝（需求 5.7）。"""
    d = tmp_path_factory.mktemp("cfmutex")

    barrier = threading.Event()

    class SlowClient:
        calls = 0

        def fetch_domains(self):
            SlowClient.calls += 1
            barrier.wait(timeout=5)  # 阻塞，保持同步进行中
            return ["a.b.com"]

    db_path = d / "cf.db"
    store = DataStore(str(db_path))
    store.initialize()
    domain_service = DomainService(store, clock=lambda: date(2026, 6, 1))
    domain_service.load()
    sync = CloudflareSync(domain_service, client_factory=lambda: SlowClient())

    results = {}

    def first():
        results["first"] = sync.sync()

    t = threading.Thread(target=first)
    t.start()
    # 等第一个同步进入 fetch（持锁）。
    time.sleep(0.2)
    # 第二次同步应被互斥拒绝。
    second = sync.sync()
    assert second.is_err
    assert second.error.code == ErrorCode.SYNC_IN_PROGRESS

    # 放行第一个同步。
    barrier.set()
    t.join(timeout=5)
    assert results["first"].is_ok
