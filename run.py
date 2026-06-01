"""Domain_Manager 启动入口。

用法（开发）：
    set SECRET_KEY=...            # 会话密钥
    set DM_ENCRYPTION_KEY=...     # Fernet 加密主密钥（python -m domain_manager.tools.genkey 生成）
    set DM_ADMIN_PASSWORD=...     # 首次启动的管理员密码
    python run.py

生产部署须置于 HTTPS（TLS）反向代理之后，并以单进程方式运行（见 design.md 并发模型）。
"""
from __future__ import annotations

import os

from apscheduler.schedulers.background import BackgroundScheduler

from domain_manager import crypto
from domain_manager.scheduler import create_scheduler
from domain_manager.web.app import create_app


def main():
    # 加密主密钥必须存在，否则无法安全存储凭证。
    if not os.environ.get(crypto.ENV_KEY):
        generated = crypto.generate_key()
        raise SystemExit(
            f"缺少环境变量 {crypto.ENV_KEY}。请设置一个 Fernet 主密钥后重试。\n"
            f"可使用以下随机生成的密钥（请妥善保存）：\n  {generated}"
        )

    app = create_app()

    # 启动后台提醒调度（需求 3.6）。单进程模型下随 Web 进程运行。
    reminder_service = app.config["REMINDER_SERVICE"]
    scheduler: BackgroundScheduler = create_scheduler(reminder_service)
    scheduler.start()
    app.config["SCHEDULER"] = scheduler

    host = os.environ.get("DM_HOST", "127.0.0.1")
    port = int(os.environ.get("DM_PORT", "5000"))
    try:
        app.run(host=host, port=port, use_reloader=False)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
