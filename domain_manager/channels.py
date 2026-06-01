"""通知渠道实现：InPageChannel 与 EmailChannel（需求 4.1、4.2）。"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Callable, List, Optional

from .models import DomainRecord, DomainStatus, NotificationSettings
from .notification import ChannelResult, NotificationChannel, ReminderPayload

# 邮件发送超时（需求 4.2 / 3.5：30 秒内未确认成功视为失败）。
EMAIL_TIMEOUT_SECONDS = 30


class InPageChannel(NotificationChannel):
    """页面内提醒渠道（需求 4.1）。

    维护一个待展示的提醒集合，Web_Interface 据此集中展示处于
    Expiring/Expired 状态的域名。send 将载荷加入集合并立即视为成功。
    """

    name = "in_page"

    def __init__(self, enabled: bool = True):
        self._enabled = enabled
        self._pending: List[ReminderPayload] = []

    def is_enabled(self) -> bool:
        return self._enabled

    def send(self, payload: ReminderPayload) -> ChannelResult:
        self._pending.append(payload)
        return ChannelResult(ok=True)

    @property
    def pending(self) -> List[ReminderPayload]:
        return list(self._pending)

    def clear(self) -> None:
        self._pending = []

    @staticmethod
    def collect_alerts(records: List[DomainRecord]) -> List[DomainRecord]:
        """返回需要在页面内展示的记录集合（需求 4.1）。

        恰好等于状态为 Expiring 或 Expired 的记录集合。
        """
        return [
            r
            for r in records
            if r.status in (DomainStatus.EXPIRING, DomainStatus.EXPIRED)
        ]


class EmailChannel(NotificationChannel):
    """电子邮件渠道（需求 4.2）。

    通过 SMTP 发送提醒；连接/发送设置 30 秒超时（需求 4.2/3.5）。
    smtp_sender 可注入以便测试（替代真实 smtplib.SMTP）。
    """

    name = "email"

    def __init__(
        self,
        settings: NotificationSettings,
        password: Optional[str],
        smtp_factory: Optional[Callable] = None,
    ):
        self._settings = settings
        self._password = password
        # 工厂返回一个支持上下文管理与 login/send_message 的 SMTP 客户端。
        self._smtp_factory = smtp_factory or self._default_smtp_factory

    def is_enabled(self) -> bool:
        return self._settings.email_enabled

    def _default_smtp_factory(self):
        return smtplib.SMTP(
            self._settings.smtp_host,
            self._settings.smtp_port,
            timeout=EMAIL_TIMEOUT_SECONDS,
        )

    def send(self, payload: ReminderPayload) -> ChannelResult:
        msg = EmailMessage()
        msg["Subject"] = payload.render_subject()
        msg["From"] = self._settings.smtp_username
        msg["To"] = self._settings.email_to
        msg.set_content(payload.render_body())
        try:
            client = self._smtp_factory()
            try:
                client.starttls()
            except (smtplib.SMTPException, AttributeError):
                # 服务器不支持 STARTTLS 时跳过（如测试桩或已是 SMTPS）。
                pass
            try:
                if self._settings.smtp_username and self._password:
                    client.login(self._settings.smtp_username, self._password)
                client.send_message(msg)
            finally:
                try:
                    client.quit()
                except Exception:
                    pass
            return ChannelResult(ok=True)
        except (smtplib.SMTPException, OSError, TimeoutError) as exc:
            return ChannelResult(ok=False, message=f"邮件发送失败：{exc}")
