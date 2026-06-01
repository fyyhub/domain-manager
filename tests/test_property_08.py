# Feature: domain-manager, Property 8: 提醒阈值触发选择正确
"""Property 8: 提醒阈值触发选择正确。

对任意域名记录、已配置阈值集合与已发送集合，select_due_thresholds 返回的每个阈值 t
都满足：剩余整天数 ≤ t、且大于下一个更小的已配置阈值（若不存在更小阈值则剩余整天数 ≥ 0），
且 (域名, t) 尚未发送；反之所有满足该条件的阈值都被返回。

Validates: Requirements 3.2
"""
from datetime import date, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.models import DomainRecord
from domain_manager.reminders import select_due_thresholds

_TODAY = date(2026, 6, 1)


@settings(max_examples=200)
@given(
    offset=st.integers(min_value=-50, max_value=400),
    thresholds=st.lists(
        st.integers(min_value=1, max_value=365), min_size=1, max_size=8, unique=True
    ),
    sent_thresholds=st.lists(st.integers(min_value=1, max_value=365), max_size=8),
)
def test_select_due_thresholds(offset, thresholds, sent_thresholds):
    rec = DomainRecord(name="a.b.com", expiration_date=_TODAY + timedelta(days=offset))
    sent_keys = {(rec.id, t) for t in sent_thresholds}

    due = select_due_thresholds(rec, thresholds, sent_keys, _TODAY)

    ordered = sorted(set(thresholds))
    remaining = offset

    # 独立地重算期望集合。
    expected = []
    if remaining >= 0:
        for t in ordered:
            smaller = [x for x in ordered if x < t]
            lower = max(smaller) if smaller else None
            in_band = remaining <= t and (lower is None or remaining > lower)
            if in_band and (rec.id, t) not in sent_keys:
                expected.append(t)

    assert sorted(due) == sorted(expected)

    # 已过期（remaining<0）不触发档位提醒。
    if remaining < 0:
        assert due == []

    # 返回的阈值都未发送且落在正确区间。
    for t in due:
        assert (rec.id, t) not in sent_keys
        assert remaining <= t
