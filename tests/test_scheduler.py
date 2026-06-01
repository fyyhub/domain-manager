"""调度器集成测试（任务 10.8，需求 3.6）。

断言提醒检查调度间隔 ≤ 24 小时，且越界配置被拒绝。
"""
import pytest

from domain_manager.scheduler import (
    REMINDER_CHECK_INTERVAL_HOURS,
    create_scheduler,
    get_reminder_interval_hours,
)


class _FakeReminder:
    def run_reminder_check(self, now=None):
        return None


def test_scheduler_interval_within_24h():
    scheduler = create_scheduler(_FakeReminder())
    try:
        hours = get_reminder_interval_hours(scheduler)
        assert hours <= 24
        assert hours == REMINDER_CHECK_INTERVAL_HOURS
    finally:
        scheduler.shutdown(wait=False) if scheduler.running else None


def test_scheduler_rejects_interval_over_24h():
    with pytest.raises(ValueError):
        create_scheduler(_FakeReminder(), interval_hours=25)


def test_custom_interval_accepted():
    scheduler = create_scheduler(_FakeReminder(), interval_hours=6)
    try:
        assert get_reminder_interval_hours(scheduler) == 6
    finally:
        scheduler.shutdown(wait=False) if scheduler.running else None
