# Feature: domain-manager, Property 13: 通知/邮件配置完整性校验
"""Property 13: 通知/邮件配置完整性校验。

对任意通知设置，当启用电子邮件但邮件服务器地址、端口、发件账户、认证凭据中任一项缺失时，
update_notification_settings 应拒绝保存、返回配置不完整/无效错误，并保留先前配置不变。

Validates: Requirements 4.4, 7.4
"""
import os

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager import crypto
from domain_manager.config_service import ConfigService, NotificationInput
from domain_manager.models import ErrorCode
from domain_manager.store import DataStore

_KEY = crypto.generate_key()
_optional_str = st.one_of(st.just(""), st.text(min_size=1, max_size=10))
_optional_port = st.one_of(st.none(), st.just(0), st.integers(min_value=1, max_value=65535))
_optional_cred = st.one_of(st.none(), st.just(""), st.text(min_size=1, max_size=10))


@settings(max_examples=200, deadline=None)
@given(
    host=_optional_str,
    port=_optional_port,
    username=_optional_str,
    credential=_optional_cred,
)
def test_email_completeness(tmp_path_factory, host, port, username, credential):
    d = tmp_path_factory.mktemp("p13")
    store = DataStore(os.path.join(str(d), "p13.db"))
    store.initialize()
    svc = ConfigService(store, encryption_key=_KEY)
    svc.load()
    before = svc.config.notification

    settings_in = NotificationInput(
        in_page_enabled=True,
        email_enabled=True,
        smtp_host=host,
        smtp_port=port,
        smtp_username=username,
        smtp_credential=credential,
        email_to="me@example.com",
    )
    res = svc.update_notification_settings(settings_in)

    complete = bool(host) and bool(port) and bool(username) and bool(credential)
    if complete:
        assert res.is_ok
        assert svc.config.notification.email_enabled is True
    else:
        assert res.is_err
        assert res.error.code == ErrorCode.INVALID_NOTIFICATION
        # 先前配置保持不变。
        assert svc.config.notification is before
