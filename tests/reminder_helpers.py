"""Reminder_Service 测试辅助：可控渠道与服务装配。"""
import os
from datetime import date

from domain_manager.channels import InPageChannel
from domain_manager.config_service import ConfigService
from domain_manager.domain_service import DomainInput, DomainService
from domain_manager.notification import ChannelResult, NotificationChannel
from domain_manager.reminders import ReminderService
from domain_manager.store import DataStore


class CountingChannel(NotificationChannel):
    """记录发送次数、可配置成功/失败的渠道。"""

    def __init__(self, name="counting", enabled=True, succeed=True):
        self.name = name
        self._enabled = enabled
        self._succeed = succeed
        self.sent = []

    def is_enabled(self):
        return self._enabled

    def set_succeed(self, value: bool):
        self._succeed = value

    def send(self, payload):
        self.sent.append(payload)
        return ChannelResult(ok=self._succeed)


def build_reminder_service(tmp_dir, domains, thresholds, channels, clock):
    """装配一个 ReminderService，并预置域名与阈值配置。

    domains: list of (name, expiration_date)
    clock: callable -> datetime
    """
    db_path = os.path.join(str(tmp_dir), "rem.db")
    store = DataStore(db_path)
    store.initialize()

    today = clock().date()
    domain_service = DomainService(store, clock=lambda: today)
    domain_service.load()
    for name, exp in domains:
        domain_service.create_domain(DomainInput(name=name, expiration_date=exp.isoformat()))

    config_service = ConfigService(store)
    config_service.load()
    config_service.update_reminder_thresholds(thresholds)

    reminder = ReminderService(
        store, domain_service, config_service, channels, clock=clock
    )
    return reminder, store, domain_service
