# Feature: domain-manager, Property 18: 数据文件损坏时保持原文件且不加载
"""Property 18: 数据文件损坏时保持原文件且不加载。

对任意损坏（无法解析）的存储文件字节内容，load_all_domains 返回数据读取失败错误、
不加载任何记录，且存储文件的字节内容保持原封不动（不被覆盖或清空）。

Validates: Requirements 6.4
"""
import os

from hypothesis import given, settings
from hypothesis import strategies as st

from domain_manager.models import ErrorCode
from domain_manager.store import DataStore


def _make_corrupt_bytes(payload: bytes) -> bytes:
    # 确保不是合法 SQLite 文件：SQLite 合法文件以 b"SQLite format 3\x00" 开头。
    # 这里前缀一段非法 magic，保证无法被解析为数据库。
    return b"NOT_A_SQLITE_DB\x00" + payload


@settings(max_examples=100)
@given(payload=st.binary(min_size=0, max_size=512))
def test_corrupt_file_preserved_and_not_loaded(tmp_path_factory, payload):
    corrupt = _make_corrupt_bytes(payload)
    d = tmp_path_factory.mktemp("store")
    db_path = os.path.join(str(d), "corrupt.db")
    with open(db_path, "wb") as f:
        f.write(corrupt)

    before = open(db_path, "rb").read()

    store = DataStore(db_path)
    result = store.load_all_domains()

    # 返回数据读取失败错误，不加载任何记录。
    assert result.is_err
    assert result.error.code == ErrorCode.STORE_CORRUPT
    assert result.value is None

    # 原文件字节保持原封不动（未被覆盖或清空）。
    after = open(db_path, "rb").read()
    assert after == before
