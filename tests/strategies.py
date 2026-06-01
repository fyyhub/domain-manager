"""Hypothesis 生成器复用（域名名称、日期等）。"""
from datetime import date

from hypothesis import strategies as st

# 合法三级域名标签。
_label = st.from_regex(r"[a-z][a-z0-9]{0,8}", fullmatch=True)


@st.composite
def valid_domain_names(draw):
    """生成合法的三级域名（至少 3 段）。"""
    n = draw(st.integers(min_value=3, max_value=4))
    labels = [draw(_label) for _ in range(n)]
    return ".".join(labels)


@st.composite
def invalid_domain_names(draw):
    """生成非法域名名称。"""
    return draw(
        st.sampled_from(
            [
                "",
                "example.com",      # 仅二级
                "localhost",        # 无点
                "sub..example.com", # 空标签
                "-bad.example.com",
                "bad-.example.com",
                "sub.exa mple.com",
                "sub.exa_mple.com",
                "a" * 300 + ".b.com",  # 超长
            ]
        )
    )


valid_dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31))


@st.composite
def invalid_dates(draw):
    """生成非法到期时间。"""
    return draw(
        st.sampled_from(
            [None, "", "not-a-date", "2030-13-01", "2030-02-30", "2023-02-29", "01/01/2030"]
        )
    )
