# Feature: domain-manager, Property 4: 状态计算全分支正确
"""Property 4: 状态计算全分支正确。

对任意到期时间（可为空）、当前日期与 status_threshold，compute_status 满足：
到期为空 -> Active；令 d 为按整日历日向下取整的剩余天数（可为负），
d < 0 -> Expired；0 <= d <= threshold -> Expiring；d > threshold -> Active。

Validates: Requirements 2.3, 2.6, 2.7, 2.8, 2.9
"""
from datetime import date, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.models import DomainStatus
from domain_manager.status import compute_status, status_remaining_days

# 在合理范围内取日期，避免 date 溢出。
_dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31))
_thresholds = st.integers(min_value=1, max_value=365)
# 相对今天的偏移天数，覆盖过去/今天/未来与阈值边界附近。
_offsets = st.integers(min_value=-1000, max_value=1000)


@settings(max_examples=200)
@given(today=_dates, offset=_offsets, threshold=_thresholds)
def test_status_all_branches(today, offset, threshold):
    try:
        expiration = today + timedelta(days=offset)
    except OverflowError:
        return  # 超出 date 范围的组合跳过
    status = compute_status(expiration, today, threshold)
    d = status_remaining_days(expiration, today)
    assert d == offset
    if d < 0:
        assert status is DomainStatus.EXPIRED
    elif 0 <= d <= threshold:
        assert status is DomainStatus.EXPIRING
    else:  # d > threshold
        assert status is DomainStatus.ACTIVE


@settings(max_examples=100)
@given(today=_dates, threshold=_thresholds)
def test_status_none_expiration_is_active(today, threshold):
    # 到期时间为空 -> Active（需求 2.9）
    assert compute_status(None, today, threshold) is DomainStatus.ACTIVE
    assert status_remaining_days(None, today) is None
