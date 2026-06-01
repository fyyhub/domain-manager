# Feature: domain-manager, Property 12: 提醒内容包含必要信息且剩余天数非负
"""Property 12: 提醒内容包含必要信息且剩余天数非负。

对任意 ReminderPayload，渲染出的提醒内容都包含域名名称、Expiration_Date，以及剩余天数；
其中剩余天数等于 max(0, ceil(Expiration_Date − 当前日期))。

Validates: Requirements 4.3
"""
from datetime import date, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.notification import build_payload, reminder_remaining_days

_dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31))
_offsets = st.integers(min_value=-1000, max_value=1000)
_names = st.from_regex(r"[a-z]{1,6}\.[a-z]{1,6}\.[a-z]{2,4}", fullmatch=True)


@settings(max_examples=200)
@given(name=_names, today=_dates, offset=_offsets)
def test_reminder_content(name, today, offset):
    try:
        expiration = today + timedelta(days=offset)
    except OverflowError:
        return
    payload = build_payload(name, expiration, today)

    # 剩余天数 = max(0, ceil(差值))，对整日差即 max(0, offset)。
    expected_days = max(0, offset)
    assert payload.remaining_days == expected_days
    assert reminder_remaining_days(expiration, today) == expected_days
    assert payload.remaining_days >= 0

    body = payload.render_body()
    # 内容包含域名名称、到期时间、剩余天数。
    assert name in body
    assert expiration.isoformat() in body
    assert str(expected_days) in body


@settings(max_examples=50)
@given(name=_names, today=_dates)
def test_reminder_content_missing_expiration(name, today):
    payload = build_payload(name, None, today)
    assert payload.remaining_days == 0
    body = payload.render_body()
    assert name in body
