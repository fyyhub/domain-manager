"""Flask 应用工厂与服务装配（需求 6.2/6.3/6.6、9.7）。"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from flask import Flask, jsonify

from .. import crypto
from ..auth import AuthService
from ..channels import EmailChannel, InPageChannel
from ..cloudflare import CloudflareClient, CloudflareSync
from ..config_service import ConfigService
from ..domain_service import DomainService
from ..reminders import ReminderService
from ..store import DataStore
from .auth_views import auth_bp
from .config_views import config_bp
from .domain_views import domains_bp

# 默认管理员账户环境变量名（首次启动创建）。生产部署应通过环境变量覆盖。
ENV_ADMIN_USER = "DM_ADMIN_USER"
ENV_ADMIN_PASSWORD = "DM_ADMIN_PASSWORD"


def create_app(
    db_path: Optional[str] = None,
    encryption_key: Optional[str] = None,
    clock=None,
    secret_key: Optional[str] = None,
) -> Flask:
    """创建并配置 Flask 应用。"""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = (
        secret_key or os.environ.get("SECRET_KEY") or os.urandom(32).hex()
    )

    db_path = db_path or os.environ.get("DM_DB_PATH", "domain_manager.db")
    enc_key = encryption_key or os.environ.get(crypto.ENV_KEY)
    clock = clock or datetime.now

    store = DataStore(db_path)
    init = store.initialize()
    if init.is_err:
        # 数据存储损坏：拒绝启动并暴露明确错误（需求 6.4）。
        raise RuntimeError(f"无法初始化数据存储：{init.error.message}")

    # 装配各服务。
    domain_service = DomainService(store, clock=lambda: clock().date())
    config_service = ConfigService(store, encryption_key=enc_key)
    auth_service = AuthService(store, clock=clock)

    load = domain_service.load()
    if load.is_err:
        raise RuntimeError(f"无法加载域名数据：{load.error.message}")
    config_service.load()
    # 应用已保存的状态阈值。
    domain_service.set_status_threshold(config_service.config.status_threshold)

    # 首次启动创建默认管理员（需求 9.7）。读取环境变量在运行时进行，
    # 以便部署或测试在调用 create_app 前设置覆盖值。
    admin_user = os.environ.get(ENV_ADMIN_USER, "admin")
    admin_password = os.environ.get(ENV_ADMIN_PASSWORD, "changeme")
    auth_service.ensure_admin(admin_user, admin_password)

    # 通知渠道。
    in_page = InPageChannel(enabled=config_service.config.notification.in_page_enabled)
    channels = [in_page]
    if config_service.config.notification.email_enabled:
        smtp_pw = crypto.decrypt_credential(
            config_service.config.notification.smtp_credential_encrypted, enc_key
        )
        channels.append(EmailChannel(config_service.config.notification, smtp_pw))

    reminder_service = ReminderService(
        store, domain_service, config_service, channels, clock=clock
    )

    # Cloudflare 同步（仅在配置了凭证时）。
    cf_sync = None
    cf_token = crypto.decrypt_credential(
        config_service.config.cloudflare_token_encrypted, enc_key
    )
    if cf_token:
        cf_sync = CloudflareSync(
            domain_service, client_factory=lambda: CloudflareClient(cf_token)
        )

    # 注入到 app.config 供视图使用。
    app.config["STORE"] = store
    app.config["DOMAIN_SERVICE"] = domain_service
    app.config["CONFIG_SERVICE"] = config_service
    app.config["AUTH_SERVICE"] = auth_service
    app.config["REMINDER_SERVICE"] = reminder_service
    app.config["CLOUDFLARE_SYNC"] = cf_sync
    app.config["IN_PAGE_CHANNEL"] = in_page
    app.config["CLOCK"] = clock

    # 注册蓝图。
    app.register_blueprint(auth_bp)
    app.register_blueprint(domains_bp)
    app.register_blueprint(config_bp)

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    return app
