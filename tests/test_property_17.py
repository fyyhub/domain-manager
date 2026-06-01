# Feature: domain-manager, Property 17: 配置保存往返一致
"""Property 17: 配置保存往返一致。

对任意合法配置，保存后重新读取得到的配置与所保存的等价，且后续操作使用新配置。

Validates: Requirements 7.2
"""
import os

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager import crypto
from domain_manager.config_service import ConfigService
from domain_manager.store import DataStore

_KEY = crypto.generate_key()


@settings(max_examples=100, deadline=None)
@given(
    status_threshold=st.integers(min_value=1, max_value=365),
    thresholds=st.lists(
        st.integers(min_value=1, max_value=3650), min_size=1, max_size=10, unique=True
    ),
    cf_token=st.text(
        alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=40
    ),
)
def test_config_roundtrip(tmp_path_factory, status_threshold, thresholds, cf_token):
    d = tmp_path_factory.mktemp("p17")
    db_path = os.path.join(str(d), "p17.db")
    store = DataStore(db_path)
    store.initialize()

    svc = ConfigService(store, encryption_key=_KEY)
    svc.load()
    assert svc.update_reminder_threshold(status_threshold).is_ok
    assert svc.update_reminder_thresholds(thresholds).is_ok
    assert svc.update_cloudflare_credentials(cf_token).is_ok

    # 用新 service 从磁盘重新加载。
    reloaded = ConfigService(DataStore(db_path), encryption_key=_KEY)
    assert reloaded.load().is_ok
    assert reloaded.config.status_threshold == status_threshold
    assert reloaded.config.reminder_thresholds == thresholds
    # Cloudflare 凭证解密后等于原文。
    assert (
        crypto.decrypt_credential(reloaded.config.cloudflare_token_encrypted, _KEY) == cf_token
    )
