# Feature: domain-manager, Property 6: status_threshold 校验
"""Property 6: status_threshold 校验。

对任意整数取值，update_reminder_threshold 当且仅当取值为 1 到 365（含两端）的整数时接受；
越界或非整数取值一律被拒绝，且被拒绝时现存配置保持不变。

Validates: Requirements 2.4, 7.3
"""
import os

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.config_service import (
    STATUS_THRESHOLD_MAX,
    STATUS_THRESHOLD_MIN,
    ConfigService,
)
from domain_manager.models import ErrorCode
from domain_manager.store import DataStore

_values = st.one_of(
    st.integers(min_value=-100, max_value=500),
    st.sampled_from([0, 1, 365, 366, -1]),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=4),
    st.booleans(),
)


def _service(tmp_path_factory):
    d = tmp_path_factory.mktemp("p06")
    store = DataStore(os.path.join(str(d), "p06.db"))
    store.initialize()
    svc = ConfigService(store)
    svc.load()
    return svc


@settings(max_examples=200, deadline=None)
@given(value=_values)
def test_status_threshold_validation(tmp_path_factory, value):
    svc = _service(tmp_path_factory)
    before = svc.config.status_threshold

    res = svc.update_reminder_threshold(value)

    is_valid_int = (
        isinstance(value, int)
        and not isinstance(value, bool)
        and STATUS_THRESHOLD_MIN <= value <= STATUS_THRESHOLD_MAX
    )
    if is_valid_int:
        assert res.is_ok
        assert svc.config.status_threshold == value
    else:
        assert res.is_err
        assert res.error.code == ErrorCode.INVALID_THRESHOLD
        # 现存配置保持不变。
        assert svc.config.status_threshold == before
