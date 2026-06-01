"""应用装配与启动集成测试（任务 14.2，需求 6.2/6.3/6.6、8.9）。

验证：文件不存在创建空库、空库零记录正常启动、启动加载在 5 秒内完成、
≤1000 条列表 3 秒内渲染。
"""
import os
import time
from datetime import date, datetime

from domain_manager.domain_service import DomainInput
from tests.web_helpers import login, make_app

_FIXED = datetime(2026, 6, 1, 12, 0, 0)


def test_missing_db_creates_empty_store_and_starts(tmp_path):
    # 数据库文件尚不存在。
    db_marker = tmp_path / "web.db"
    assert not db_marker.exists()
    app = make_app(tmp_path, clock=lambda: _FIXED)
    # 空库正常启动：健康检查可用，域名列表为空。
    client = app.test_client()
    assert client.get("/healthz").status_code == 200
    login(client)
    resp = client.get("/domains")
    assert resp.status_code == 200
    assert "暂无记录" in resp.get_data(as_text=True)


def test_startup_loads_within_5_seconds(tmp_path):
    # 预置一些数据，重建 app 测量加载时间。
    app = make_app(tmp_path, clock=lambda: _FIXED)
    service = app.config["DOMAIN_SERVICE"]
    for i in range(50):
        service.create_domain(
            DomainInput(name=f"d{i}.example.com", expiration_date="2030-01-01")
        )
    db_path = app.config["STORE"].path

    from domain_manager import crypto
    from domain_manager.web.app import create_app

    start = time.perf_counter()
    app2 = create_app(
        db_path=db_path,
        encryption_key=crypto.generate_key(),
        clock=lambda: _FIXED,
        secret_key="s",
    )
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0
    assert len(app2.config["DOMAIN_SERVICE"].records_snapshot) == 50


def test_list_renders_1000_records_within_3_seconds(tmp_path):
    app = make_app(tmp_path, clock=lambda: _FIXED)
    service = app.config["DOMAIN_SERVICE"]
    for i in range(1000):
        service.create_domain(
            DomainInput(name=f"d{i}.example.com", expiration_date="2030-01-01")
        )
    client = app.test_client()
    login(client)

    start = time.perf_counter()
    resp = client.get("/domains")
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    assert elapsed < 3.0
