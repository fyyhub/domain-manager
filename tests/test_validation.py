"""校验纯函数的单元测试（任务 2.3，需求 1.6、1.7）。

覆盖空串、超长（>253）、非法字符、合法三级域名，以及合法/非法日历日期。
"""
from datetime import date

import pytest

from domain_manager.validation import (
    MAX_DOMAIN_LENGTH,
    is_valid_domain_name,
    is_valid_expiration_date,
    parse_date,
)


# --------------------------------------------------------------------------- #
# is_valid_domain_name（需求 1.6）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name",
    [
        "sub.example.com",
        "a.b.c",
        "my-app.example.co.uk",
        "x1.y2.z3.example.com",
        "node-1.cluster.example.org",
    ],
)
def test_valid_third_level_domains(name):
    assert is_valid_domain_name(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "",                      # 空串
        "example.com",          # 仅二级，不是三级
        "localhost",            # 无点
        "sub..example.com",     # 空标签
        "-bad.example.com",     # 标签以连字符开头
        "bad-.example.com",     # 标签以连字符结尾
        "sub.exa mple.com",     # 含空格
        "sub.exa_mple.com",     # 含下划线（非法字符）
        "sub.例子.com",          # 非 ASCII（未做 IDN 转换）
    ],
)
def test_invalid_domain_names(name):
    assert is_valid_domain_name(name) is False


def test_domain_name_too_long_rejected():
    # 构造一个 >253 字符但格式看似合法的域名
    label = "a" * 60
    long_name = ".".join([label, label, label, label, label])  # 远超 253
    assert len(long_name) > MAX_DOMAIN_LENGTH
    assert is_valid_domain_name(long_name) is False


def test_domain_name_non_string_rejected():
    assert is_valid_domain_name(None) is False
    assert is_valid_domain_name(12345) is False


# --------------------------------------------------------------------------- #
# is_valid_expiration_date / parse_date（需求 1.7）
# --------------------------------------------------------------------------- #
def test_valid_expiration_date_object():
    assert is_valid_expiration_date(date(2030, 1, 1)) is True


@pytest.mark.parametrize(
    "value",
    ["2030-01-01", "2026-12-31", "2024-02-29"],  # 含合法闰年日期
)
def test_valid_expiration_date_iso_strings(value):
    assert is_valid_expiration_date(value) is True


@pytest.mark.parametrize(
    "value",
    [
        None,            # 空
        "",              # 空串
        "not-a-date",   # 非日期
        "2030-13-01",   # 非法月份
        "2030-02-30",   # 非法日期
        "2023-02-29",   # 平年无 2/29
        "01/01/2030",   # 错误格式
        12345,           # 非字符串/非 date
    ],
)
def test_invalid_expiration_dates(value):
    assert is_valid_expiration_date(value) is False


def test_parse_date_roundtrip():
    assert parse_date("2030-06-15") == date(2030, 6, 15)
    assert parse_date(date(2030, 6, 15)) == date(2030, 6, 15)
    assert parse_date("garbage") is None
    assert parse_date(None) is None
