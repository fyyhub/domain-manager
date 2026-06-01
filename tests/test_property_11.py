# Feature: domain-manager, Property 11: 页面内提醒集合等于到期/过期记录集合
"""Property 11: 页面内提醒集合等于到期/过期记录集合。

对任意域名记录集合，页面内提醒展示的集合恰好等于其中 Domain_Status 为
Expiring 或 Expired 的记录集合（无遗漏、无多余）。

Validates: Requirements 4.1
"""
from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.channels import InPageChannel
from domain_manager.models import DomainRecord, DomainStatus

_statuses = st.sampled_from(list(DomainStatus))


@st.composite
def _records(draw):
    n = draw(st.integers(min_value=0, max_value=20))
    recs = []
    for i in range(n):
        status = draw(_statuses)
        rec = DomainRecord(name=f"d{i}.example.com")
        rec.status = status
        recs.append(rec)
    return recs


@settings(max_examples=100)
@given(records=_records())
def test_in_page_alert_set(records):
    alerts = InPageChannel.collect_alerts(records)
    alert_ids = {r.id for r in alerts}
    expected_ids = {
        r.id
        for r in records
        if r.status in (DomainStatus.EXPIRING, DomainStatus.EXPIRED)
    }
    assert alert_ids == expected_ids
    # 无多余：结果中没有 Active 记录。
    assert all(r.status != DomainStatus.ACTIVE for r in alerts)
