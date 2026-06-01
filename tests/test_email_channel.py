"""EmailChannel 集成测试（任务 9.5，需求 4.2）。

使用 mock SMTP 客户端，验证发送一封含正确内容的邮件，以及发送失败时返回失败结果。
"""
from datetime import date

from domain_manager.channels import EMAIL_TIMEOUT_SECONDS, EmailChannel
from domain_manager.models import NotificationSettings
from domain_manager.notification import build_payload


class FakeSMTP:
    """记录交互的假 SMTP 客户端。"""

    instances = []

    def __init__(self, host=None, port=None, timeout=None, fail=False):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.fail = fail
        self.logged_in = False
        self.sent_messages = []
        self.quit_called = False
        FakeSMTP.instances.append(self)

    def starttls(self):
        pass

    def login(self, username, password):
        self.logged_in = True

    def send_message(self, msg):
        if self.fail:
            import smtplib

            raise smtplib.SMTPException("模拟发送失败")
        self.sent_messages.append(msg)

    def quit(self):
        self.quit_called = True


def _settings():
    return NotificationSettings(
        email_enabled=True,
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="me@example.com",
        email_to="to@example.com",
    )


def test_email_sends_with_correct_content():
    FakeSMTP.instances = []
    captured = {}

    def factory():
        c = FakeSMTP(timeout=EMAIL_TIMEOUT_SECONDS)
        captured["client"] = c
        return c

    channel = EmailChannel(_settings(), password="secret", smtp_factory=factory)
    payload = build_payload("sub.example.com", date(2030, 1, 1), date(2029, 12, 20))
    result = channel.send(payload)

    assert result.ok is True
    client = captured["client"]
    assert client.timeout == EMAIL_TIMEOUT_SECONDS  # 30 秒超时
    assert client.logged_in is True
    assert len(client.sent_messages) == 1
    msg = client.sent_messages[0]
    assert msg["To"] == "to@example.com"
    assert "sub.example.com" in msg.get_content()
    assert "2030-01-01" in msg.get_content()


def test_email_send_failure_returns_error():
    def factory():
        return FakeSMTP(fail=True)

    channel = EmailChannel(_settings(), password="secret", smtp_factory=factory)
    payload = build_payload("sub.example.com", date(2030, 1, 1), date(2029, 12, 20))
    result = channel.send(payload)
    assert result.ok is False
    assert "失败" in result.message


def test_email_channel_disabled_when_not_enabled():
    settings = _settings()
    settings.email_enabled = False
    channel = EmailChannel(settings, password=None)
    assert channel.is_enabled() is False
