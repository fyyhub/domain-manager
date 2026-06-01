"""APScheduler 调度装配（需求 3.6）。

注册提醒检查任务，调度间隔 ≤ 24 小时。调度器随 Web 进程运行（单进程模型，
见 design.md 的并发模型说明）。
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

# 提醒检查间隔（需求 3.6：至少每 24 小时一次）。这里取较短间隔以便更及时，
# 同时满足"≤ 24 小时"的约束。
REMINDER_CHECK_INTERVAL_HOURS = 12


def create_scheduler(reminder_service, interval_hours: int = REMINDER_CHECK_INTERVAL_HOURS):
    """创建并配置一个后台调度器（未启动）。

    interval_hours 必须 ≤ 24 以满足需求 3.6。
    """
    if interval_hours > 24:
        raise ValueError("提醒检查间隔不得超过 24 小时（需求 3.6）")
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        reminder_service.run_reminder_check,
        trigger="interval",
        hours=interval_hours,
        id="reminder_check",
        replace_existing=True,
        next_run_time=None,
    )
    return scheduler


def get_reminder_interval_hours(scheduler) -> float:
    """返回已注册提醒任务的调度间隔小时数（用于测试断言 ≤ 24）。"""
    job = scheduler.get_job("reminder_check")
    if job is None:
        raise LookupError("未找到 reminder_check 任务")
    interval = job.trigger.interval
    return interval.total_seconds() / 3600.0
