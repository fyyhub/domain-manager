"""Data_Store 持久化层（SQLite）。

对应 design.md Data_Store 与需求 6。

设计要点：
- 单文件 SQLite，写操作在单事务中提交，成功返回前落盘（需求 6.1）。
- 启动加载全部域名记录；文件不存在时创建空库（需求 6.2/6.3/6.6）。
- 文件损坏（无法解析为数据库）时返回 STORE_CORRUPT，不加载任何记录，
  且以只读方式打开以保证原文件字节不被覆盖/清空（需求 6.4）。
- 写入失败（磁盘满/无权限/IO 错误）返回 STORE_WRITE_FAILED（需求 6.5）。
- config/user 以 JSON 存于 kv 表；domains、reminder_sent 各自建表。
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3
from datetime import date, datetime
from typing import List, Optional

from .models import (
    AppConfig,
    DomainRecord,
    DomainStatus,
    ErrorCode,
    NotificationSettings,
    ReminderSent,
    ReminderState,
    Result,
    Source,
    User,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS domains (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    expiration_date TEXT,
    platform TEXT,
    source TEXT,
    registered_date TEXT,
    notes TEXT,
    channel TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminder_sent (
    domain_id TEXT NOT NULL,
    threshold TEXT NOT NULL,
    state TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    PRIMARY KEY (domain_id, threshold)
);
"""


# --------------------------------------------------------------------------- #
# 序列化辅助
# --------------------------------------------------------------------------- #
def _date_to_str(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d is not None else None


def _str_to_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    return date.fromisoformat(s)


def _dt_to_str(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d is not None else None


def _str_to_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    return datetime.fromisoformat(s)


def _bytes_to_b64(b: Optional[bytes]) -> Optional[str]:
    return base64.b64encode(b).decode("ascii") if b is not None else None


def _b64_to_bytes(s: Optional[str]) -> Optional[bytes]:
    return base64.b64decode(s.encode("ascii")) if s else None


class DataStore:
    """封装 SQLite 访问，提供事务化原子写与故障容错。"""

    def __init__(self, path: str):
        self.path = path

    # ----------------------------------------------------------------- #
    # 初始化与连接
    # ----------------------------------------------------------------- #
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> Result:
        """确保库文件与表结构存在（需求 6.3）。文件不存在则创建空库。"""
        try:
            conn = self._connect()
            try:
                conn.executescript(_SCHEMA)
                self._ensure_channel_column(conn)
                conn.commit()
            finally:
                conn.close()
            return Result.ok(None)
        except sqlite3.DatabaseError:
            # 已存在但无法解析为数据库 -> 损坏（需求 6.4），不改动原文件。
            return Result.fail(ErrorCode.STORE_CORRUPT, "数据存储文件损坏，无法初始化")
        except OSError as exc:
            return Result.fail(ErrorCode.STORE_WRITE_FAILED, f"初始化数据存储失败：{exc}")

    def _is_corrupt(self) -> bool:
        """以只读方式探测文件是否为合法 SQLite 数据库，不修改文件（需求 6.4）。"""
        uri = f"file:{self.path}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
            try:
                conn.execute("PRAGMA schema_version;").fetchone()
            finally:
                conn.close()
            return False
        except sqlite3.DatabaseError:
            return True
        except OSError:
            # 只读打开失败（如不存在）不视为损坏，交由上层处理。
            return False

    @staticmethod
    def _ensure_channel_column(conn: sqlite3.Connection) -> None:
        """兼容旧库：若 channel 列不存在则自动添加。"""
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(domains)").fetchall()]
        if "channel" not in cols:
            conn.execute("ALTER TABLE domains ADD COLUMN channel TEXT")

    # ----------------------------------------------------------------- #
    # 域名记录
    # ----------------------------------------------------------------- #
    def load_all_domains(self) -> Result:
        """加载全部域名记录（需求 6.2/6.6）。

        - 文件不存在：创建空库并返回空列表（需求 6.3/6.6）。
        - 文件损坏：返回 STORE_CORRUPT，不加载、不改动原文件（需求 6.4）。
        """
        if not os.path.exists(self.path):
            init = self.initialize()
            if init.is_err:
                return init
            return Result.ok([])

        if self._is_corrupt():
            return Result.fail(ErrorCode.STORE_CORRUPT, "数据存储文件损坏，无法读取")

        try:
            conn = self._connect()
            try:
                # 确保表结构存在（对已有的合法空库）。
                conn.executescript(_SCHEMA)
                self._ensure_channel_column(conn)
                conn.commit()
                rows = conn.execute("SELECT * FROM domains").fetchall()
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            return Result.fail(ErrorCode.STORE_CORRUPT, "数据存储文件损坏，无法读取")
        except OSError as exc:
            return Result.fail(ErrorCode.STORE_WRITE_FAILED, f"读取数据存储失败：{exc}")

        records = [self._row_to_record(r) for r in rows]
        return Result.ok(records)

    @staticmethod
    def _row_to_record(r: sqlite3.Row) -> DomainRecord:
        return DomainRecord(
            id=r["id"],
            name=r["name"],
            expiration_date=_str_to_date(r["expiration_date"]),
            platform=r["platform"] or "",
            source=Source(r["source"]) if r["source"] else Source.MANUAL,
            registered_date=_str_to_date(r["registered_date"]),
            notes=r["notes"] or "",
            channel=r["channel"] if "channel" in r.keys() and r["channel"] else "",
            status=DomainStatus.ACTIVE,  # 派生字段，由上层重算
            created_at=_str_to_dt(r["created_at"]),
            updated_at=_str_to_dt(r["updated_at"]),
        )

    def save_domain(self, record: DomainRecord) -> Result:
        """插入一条新域名记录（需求 6.1/6.5）。"""
        return self._write(
            "INSERT INTO domains "
            "(id, name, expiration_date, platform, source, registered_date, notes, channel, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.id,
                record.name,
                _date_to_str(record.expiration_date),
                record.platform,
                record.source.value,
                _date_to_str(record.registered_date),
                record.notes,
                record.channel,
                _dt_to_str(record.created_at),
                _dt_to_str(record.updated_at),
            ),
        )

    def update_domain(self, record: DomainRecord) -> Result:
        """更新一条已存在的域名记录（需求 6.1/6.5）。"""
        return self._write(
            "UPDATE domains SET name=?, expiration_date=?, platform=?, source=?, "
            "registered_date=?, notes=?, channel=?, created_at=?, updated_at=? WHERE id=?",
            (
                record.name,
                _date_to_str(record.expiration_date),
                record.platform,
                record.source.value,
                _date_to_str(record.registered_date),
                record.notes,
                record.channel,
                _dt_to_str(record.created_at),
                _dt_to_str(record.updated_at),
                record.id,
            ),
        )

    def delete_domain(self, domain_id: str) -> Result:
        """删除一条域名记录（需求 6.1/6.5）。"""
        return self._write("DELETE FROM domains WHERE id=?", (domain_id,))

    def _write(self, sql: str, params: tuple) -> Result:
        """在单事务中执行写操作；失败返回 STORE_WRITE_FAILED（需求 6.1/6.5）。"""
        try:
            conn = self._connect()
            try:
                conn.execute("BEGIN")
                conn.execute(sql, params)
                conn.commit()
            finally:
                conn.close()
            return Result.ok(None)
        except sqlite3.DatabaseError:
            return Result.fail(ErrorCode.STORE_CORRUPT, "数据存储文件损坏，无法写入")
        except OSError as exc:
            return Result.fail(ErrorCode.STORE_WRITE_FAILED, f"写入数据存储失败：{exc}")

    # ----------------------------------------------------------------- #
    # 配置（kv 表，JSON）
    # ----------------------------------------------------------------- #
    def save_config(self, config: AppConfig) -> Result:
        payload = {
            "status_threshold": config.status_threshold,
            "reminder_thresholds": list(config.reminder_thresholds),
            "notification": {
                "in_page_enabled": config.notification.in_page_enabled,
                "email_enabled": config.notification.email_enabled,
                "smtp_host": config.notification.smtp_host,
                "smtp_port": config.notification.smtp_port,
                "smtp_username": config.notification.smtp_username,
                "smtp_credential_encrypted": _bytes_to_b64(
                    config.notification.smtp_credential_encrypted
                ),
                "email_to": config.notification.email_to,
            },
            "cloudflare_token_encrypted": _bytes_to_b64(config.cloudflare_token_encrypted),
        }
        return self._write_kv("config", json.dumps(payload))

    def load_config(self) -> Result:
        row = self._read_kv("config")
        if row.is_err:
            return row
        if row.value is None:
            return Result.ok(AppConfig())  # 默认配置
        data = json.loads(row.value)
        n = data.get("notification", {})
        config = AppConfig(
            status_threshold=data.get("status_threshold", 30),
            reminder_thresholds=data.get("reminder_thresholds", [30, 7, 1]),
            notification=NotificationSettings(
                in_page_enabled=n.get("in_page_enabled", True),
                email_enabled=n.get("email_enabled", False),
                smtp_host=n.get("smtp_host", ""),
                smtp_port=n.get("smtp_port"),
                smtp_username=n.get("smtp_username", ""),
                smtp_credential_encrypted=_b64_to_bytes(n.get("smtp_credential_encrypted")),
                email_to=n.get("email_to", ""),
            ),
            cloudflare_token_encrypted=_b64_to_bytes(data.get("cloudflare_token_encrypted")),
        )
        return Result.ok(config)

    # ----------------------------------------------------------------- #
    # 用户（kv 表，JSON）
    # ----------------------------------------------------------------- #
    def save_user(self, user: User) -> Result:
        payload = {
            "username": user.username,
            "password_hash": user.password_hash,
            "failed_attempts": [_dt_to_str(d) for d in user.failed_attempts],
            "locked_until": _dt_to_str(user.locked_until),
        }
        return self._write_kv("user", json.dumps(payload))

    def load_user(self) -> Result:
        row = self._read_kv("user")
        if row.is_err:
            return row
        if row.value is None:
            return Result.ok(None)
        data = json.loads(row.value)
        user = User(
            username=data["username"],
            password_hash=data["password_hash"],
            failed_attempts=[_str_to_dt(s) for s in data.get("failed_attempts", [])],
            locked_until=_str_to_dt(data.get("locked_until")),
        )
        return Result.ok(user)

    # ----------------------------------------------------------------- #
    # 提醒已发送跟踪
    # ----------------------------------------------------------------- #
    def load_reminder_sent(self) -> Result:
        if not os.path.exists(self.path):
            return Result.ok([])
        if self._is_corrupt():
            return Result.fail(ErrorCode.STORE_CORRUPT, "数据存储文件损坏，无法读取")
        try:
            conn = self._connect()
            try:
                conn.executescript(_SCHEMA)
                rows = conn.execute("SELECT * FROM reminder_sent").fetchall()
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            return Result.fail(ErrorCode.STORE_CORRUPT, "数据存储文件损坏，无法读取")
        except OSError as exc:
            return Result.fail(ErrorCode.STORE_WRITE_FAILED, f"读取数据存储失败：{exc}")

        items = []
        for r in rows:
            threshold = r["threshold"]
            # 整型阈值以字符串存储，"expired" 保持原样。
            parsed = threshold if threshold == "expired" else int(threshold)
            items.append(
                ReminderSent(
                    domain_id=r["domain_id"],
                    threshold=parsed,
                    state=ReminderState(r["state"]),
                    retry_count=r["retry_count"],
                    last_attempt_at=_str_to_dt(r["last_attempt_at"]),
                )
            )
        return Result.ok(items)

    def mark_reminder_sent(self, item: ReminderSent) -> Result:
        return self._write(
            "INSERT INTO reminder_sent (domain_id, threshold, state, retry_count, last_attempt_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(domain_id, threshold) DO UPDATE SET "
            "state=excluded.state, retry_count=excluded.retry_count, "
            "last_attempt_at=excluded.last_attempt_at",
            (
                item.domain_id,
                str(item.threshold),
                item.state.value,
                item.retry_count,
                _dt_to_str(item.last_attempt_at),
            ),
        )

    # ----------------------------------------------------------------- #
    # kv 读写
    # ----------------------------------------------------------------- #
    def _write_kv(self, key: str, value: str) -> Result:
        return self._write(
            "INSERT INTO kv (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def _read_kv(self, key: str) -> Result:
        if not os.path.exists(self.path):
            init = self.initialize()
            if init.is_err:
                return init
            return Result.ok(None)
        if self._is_corrupt():
            return Result.fail(ErrorCode.STORE_CORRUPT, "数据存储文件损坏，无法读取")
        try:
            conn = self._connect()
            try:
                conn.executescript(_SCHEMA)
                row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            return Result.fail(ErrorCode.STORE_CORRUPT, "数据存储文件损坏，无法读取")
        except OSError as exc:
            return Result.fail(ErrorCode.STORE_WRITE_FAILED, f"读取数据存储失败：{exc}")
        return Result.ok(row["value"] if row else None)
