# Feature: domain-manager, Property 24: 三种状态视觉标识互不相同
"""Property 24: 三种状态视觉标识互不相同。

对任意两个不同的 Domain_Status，其对应的视觉标识互不相同
（Active、Expiring、Expired 三者两两不同）。

Validates: Requirements 8.5
"""
from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.models import DomainStatus
from domain_manager.web.domain_views import STATUS_BADGE

_statuses = st.sampled_from(list(DomainStatus))


@settings(max_examples=100)
@given(s1=_statuses, s2=_statuses)
def test_status_badges_distinct(s1, s2):
    if s1 != s2:
        assert STATUS_BADGE[s1] != STATUS_BADGE[s2]
    else:
        assert STATUS_BADGE[s1] == STATUS_BADGE[s2]


def test_all_three_badges_distinct():
    badges = {STATUS_BADGE[s] for s in DomainStatus}
    assert len(badges) == 3
