"""核心数据模型、枚举与统一 Result 类型。

对应 design.md 的 Data Models 与 Components and Interfaces 中的 Result 约定。
所有跨层返回值统一使用 Result：成功时携带值，失败时携带结构化错误（code + message）。
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Generic, Optional, TypeVar


# --------------------------------------------------------------------------- #
# 枚举
# --------------------------------------------------------------------------- #
class DomainStatus(str, enum.Enum):
    """域名生命周期状态（需求 2）。"""

    ACTIVE = "Active"
    EXPIRING = "Expiring"
    EXPIRED = "Expired"


class Source(str, enum.Enum):
    """域名记录来源（需求 5.2）。"""

    MANUAL = "Manual"
    CLOUDFLARE = "Cloudflare"


class ReminderState(str, enum.Enum):
    """提醒发送状态（design.md ReminderSent，需求 3.5）。"""

    PENDING = "Pending"
    SENT = "Sent"
    FAILED = "Failed"


# --------------------------------------------------------------------------- #
# 错误码
# --------------------------------------------------------------------------- #
class ErrorCode(str, enum.Enum):
    """机器可判别的错误码（design.md Error Handling）。"""

    DUPLICATE = "DUPLICATE"
    INVALID_NAME = "INVALID_NAME"
    INVALID_DATE = "INVALID_DATE"
    NOT_FOUND = "NOT_FOUND"
    INVALID_THRESHOLD = "INVALID_THRESHOLD"
    INVALID_NOTIFICATION = "INVALID_NOTIFICATION"
    STORE_CORRUPT = "STORE_CORRUPT"
    STORE_WRITE_FAILED = "STORE_WRITE_FAILED"
    CF_INVALID_CREDENTIALS = "CF_INVALID_CREDENTIALS"
    CF_SYNC_FAILED = "CF_SYNC_FAILED"
    SYNC_IN_PROGRESS = "SYNC_IN_PROGRESS"
    AUTH_FAILED = "AUTH_FAILED"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    SESSION_INVALID = "SESSION_INVALID"


# --------------------------------------------------------------------------- #
# Result 类型
# --------------------------------------------------------------------------- #
T = TypeVar("T")


@dataclass(frozen=True)
class Error:
    """结构化错误，含可判别 code 与可读 message。"""

    code: ErrorCode
    message: str


@dataclass(frozen=True)
class Result(Generic[T]):
    """统一返回值：成功携带 value，失败携带 error。

    使用 Result.ok(value) / Result.fail(code, message) 构造，避免直接传参出错。
    """

    value: Optional[T] = None
    error: Optional[Error] = None

    @property
    def is_ok(self) -> bool:
        return self.error is None

    @property
    def is_err(self) -> bool:
        return self.error is not None

    @staticmethod
    def ok(value: T = None) -> "Result[T]":
        return Result(value=value, error=None)

    @staticmethod
    def fail(code: ErrorCode, message: str) -> "Result[T]":
        return Result(value=None, error=Error(code=code, message=message))


# --------------------------------------------------------------------------- #
# 数据模型
# --------------------------------------------------------------------------- #
def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class DomainRecord:
    """域名记录（design.md DomainRecord）。

    status 为派生字段，不作为权威值持久化，加载/创建/更新时由 status.compute_status 重算。
    """

    name: str
    expiration_date: Optional[date] = None
    platform: str = ""
    source: Source = Source.MANUAL
    registered_date: Optional[date] = None
    notes: str = ""
    channel: str = ""
    id: str = field(default_factory=_new_id)
    status: DomainStatus = DomainStatus.ACTIVE
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def with_status(self, status: DomainStatus) -> "DomainRecord":
        """返回一个状态被替换的副本（不可变更新风格，便于测试）。"""
        return replace(self, status=status)


@dataclass
class NotificationSettings:
    """通知渠道设置（design.md NotificationSettings，需求 4）。"""

    in_page_enabled: bool = True
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: Optional[int] = None
    smtp_username: str = ""
    smtp_credential_encrypted: Optional[bytes] = None
    email_to: str = ""


# 默认提醒发送阈值（需求 3.1）。
DEFAULT_REMINDER_THRESHOLDS = [30, 7, 1]
# 默认状态计算阈值（需求 2.5）。
DEFAULT_STATUS_THRESHOLD = 30


@dataclass
class AppConfig:
    """应用配置（design.md AppConfig，需求 7）。

    status_threshold：驱动 Domain_Status 的 Expiring 边界（1–365，需求 2.4/7.3）。
    reminder_thresholds：驱动各档提醒触发（1–10 个、每个 1–3650，需求 3.1）。
    """

    status_threshold: int = DEFAULT_STATUS_THRESHOLD
    reminder_thresholds: list = field(default_factory=lambda: list(DEFAULT_REMINDER_THRESHOLDS))
    notification: NotificationSettings = field(default_factory=NotificationSettings)
    cloudflare_token_encrypted: Optional[bytes] = None


@dataclass
class User:
    """认证账户（design.md User，需求 9）。"""

    username: str
    password_hash: str
    failed_attempts: list = field(default_factory=list)  # list[datetime]
    locked_until: Optional[datetime] = None


@dataclass
class Session:
    """服务端会话（design.md Session，需求 9.3/9.5）。"""

    session_id: str
    username: str
    last_active_at: datetime


@dataclass
class ReminderSent:
    """提醒已发送跟踪（design.md ReminderSent，需求 3.3/3.4/3.5）。

    threshold 为整型阈值档位，或字符串 "expired" 表示过期提醒。
    (domain_id, threshold) 唯一，作为去重的物理保证。
    """

    domain_id: str
    threshold: object  # int | "expired"
    state: ReminderState = ReminderState.PENDING
    retry_count: int = 0
    last_attempt_at: Optional[datetime] = None
