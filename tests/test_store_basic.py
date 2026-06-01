"""Data_Store 基础冒烟测试（任务 3，需求 6.2/6.3/6.6）。

验证文件不存在创建空库、域名记录写入与回读、配置/用户/提醒往返。
"""
import os
from datetime import date, datetime

from domain_manager.models import (
    AppConfig,
    DomainRecord,
    NotificationSettings,
    ReminderSent,
    ReminderState,
    Source,
    User,
)
from domain_manager.store import DataStore


def _store(tmp_path) -> DataStore:
    return DataStore(os.path.join(str(tmp_path), "test.db"))


def test_missing_file_creates_empty_store(tmp_path):
    store = _store(tmp_path)
    result = store.load_all_domains()
    assert result.is_ok
    assert result.value == []


def test_domain_write_and_readback(tmp_path):
    store = _store(tmp_path)
    store.initialize()
    rec = DomainRecord(
        name="sub.example.com",
        expiration_date=date(2030, 1, 1),
        platform="Cloudflare",
        source=Source.MANUAL,
        notes="test",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    assert store.save_domain(rec).is_ok

    loaded = store.load_all_domains()
    assert loaded.is_ok
    assert len(loaded.value) == 1
    got = loaded.value[0]
    assert got.id == rec.id
    assert got.name == "sub.example.com"
    assert got.expiration_date == date(2030, 1, 1)
    assert got.source == Source.MANUAL


def test_domain_update_and_delete(tmp_path):
    store = _store(tmp_path)
    store.initialize()
    rec = DomainRecord(name="a.b.com", expiration_date=date(2030, 1, 1))
    store.save_domain(rec)

    rec.notes = "updated"
    rec.expiration_date = date(2031, 5, 5)
    assert store.update_domain(rec).is_ok
    got = store.load_all_domains().value[0]
    assert got.notes == "updated"
    assert got.expiration_date == date(2031, 5, 5)

    assert store.delete_domain(rec.id).is_ok
    assert store.load_all_domains().value == []


def test_config_roundtrip(tmp_path):
    store = _store(tmp_path)
    store.initialize()
    config = AppConfig(
        status_threshold=45,
        reminder_thresholds=[60, 14, 3],
        notification=NotificationSettings(
            email_enabled=True,
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_username="me",
            smtp_credential_encrypted=b"\x01\x02\x03",
            email_to="me@example.com",
        ),
        cloudflare_token_encrypted=b"\xaa\xbb",
    )
    assert store.save_config(config).is_ok
    got = store.load_config()
    assert got.is_ok
    assert got.value.status_threshold == 45
    assert got.value.reminder_thresholds == [60, 14, 3]
    assert got.value.notification.smtp_port == 587
    assert got.value.notification.smtp_credential_encrypted == b"\x01\x02\x03"
    assert got.value.cloudflare_token_encrypted == b"\xaa\xbb"


def test_default_config_when_absent(tmp_path):
    store = _store(tmp_path)
    store.initialize()
    got = store.load_config()
    assert got.is_ok
    assert got.value.status_threshold == 30
    assert got.value.reminder_thresholds == [30, 7, 1]


def test_user_roundtrip(tmp_path):
    store = _store(tmp_path)
    store.initialize()
    user = User(
        username="admin",
        password_hash="hash123",
        failed_attempts=[datetime(2026, 1, 1, 10, 0, 0)],
        locked_until=None,
    )
    assert store.save_user(user).is_ok
    got = store.load_user()
    assert got.is_ok
    assert got.value.username == "admin"
    assert got.value.password_hash == "hash123"
    assert len(got.value.failed_attempts) == 1


def test_reminder_sent_roundtrip_and_upsert(tmp_path):
    store = _store(tmp_path)
    store.initialize()
    item = ReminderSent(domain_id="d1", threshold=30, state=ReminderState.SENT, retry_count=0)
    assert store.mark_reminder_sent(item).is_ok

    expired = ReminderSent(domain_id="d1", threshold="expired", state=ReminderState.SENT)
    assert store.mark_reminder_sent(expired).is_ok

    items = store.load_reminder_sent()
    assert items.is_ok
    assert len(items.value) == 2
    thresholds = {i.threshold for i in items.value}
    assert thresholds == {30, "expired"}

    # upsert：同一 (domain, threshold) 更新而非重复插入。
    item.retry_count = 2
    item.state = ReminderState.PENDING
    store.mark_reminder_sent(item)
    items = store.load_reminder_sent()
    assert len(items.value) == 2
    d1_30 = [i for i in items.value if i.threshold == 30][0]
    assert d1_30.retry_count == 2
