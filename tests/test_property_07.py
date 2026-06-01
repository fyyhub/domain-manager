# Feature: domain-manager, Property 7: reminder_thresholds 校验
"""Property 7: reminder_thresholds 校验。

对任意阈值列表，update_reminder_thresholds 当且仅当列表含 1–10 个元素、每个元素为
1–3650 的整数、且元素互不重复时接受；任一条件不满足则拒绝并返回具体校验失败原因，
且现存配置保持不变。

Validates: Requirements 3.1, 3.7
"""
import os

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.config_service import (
    REMINDER_THRESHOLD_MAX,
    REMINDER_THRESHOLD_MIN,
    REMINDER_THRESHOLDS_MAX_COUNT,
    ConfigService,
)
from domain_manager.models import ErrorCode
from domain_manager.store import DataStore

# 元素可能越界，列表长度可能为 0 或 >10，可能含重复。
_element = st.one_of(
    st.integers(min_value=-50, max_value=4000),
    st.sampled_from([0, 1, 3650, 3651]),
)
_lists = st.lists(_element, min_size=0, max_size=13)


def _is_valid(values) -> bool:
    if not (1 <= len(values) <= REMINDER_THRESHOLDS_MAX_COUNT):
        return False
    if len(set(values)) != len(values):
        return False
    return all(
        isinstance(v, int)
        and not isinstance(v, bool)
        and REMINDER_THRESHOLD_MIN <= v <= REMINDER_THRESHOLD_MAX
        for v in values
    )


@settings(max_examples=200, deadline=None)
@given(values=_lists)
def test_reminder_thresholds_validation(tmp_path_factory, values):
    d = tmp_path_factory.mktemp("p07")
    store = DataStore(os.path.join(str(d), "p07.db"))
    store.initialize()
    svc = ConfigService(store)
    svc.load()
    before = list(svc.config.reminder_thresholds)

    res = svc.update_reminder_thresholds(values)

    if _is_valid(values):
        assert res.is_ok
        assert svc.config.reminder_thresholds == [int(v) for v in values]
    else:
        assert res.is_err
        assert res.error.code == ErrorCode.INVALID_THRESHOLD
        assert svc.config.reminder_thresholds == before
