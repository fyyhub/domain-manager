"""Config_Service：配置管理（需求 2.4/2.5、3.1/3.7、4.4、7）。

负责 status_threshold、reminder_thresholds、通知设置（含邮件完整性校验）与
Cloudflare 凭证（加密存储）的读写与校验。get_config 返回的凭证字段以掩码呈现。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from . import crypto
from .models import (
    AppConfig,
    ErrorCode,
    NotificationSettings,
    Result,
)
from .store import DataStore

# 阈值范围常量。
STATUS_THRESHOLD_MIN = 1
STATUS_THRESHOLD_MAX = 365
REMINDER_THRESHOLD_MIN = 1
REMINDER_THRESHOLD_MAX = 3650
REMINDER_THRESHOLDS_MAX_COUNT = 10


@dataclass
class NotificationInput:
    """通知设置输入（明文凭据，由服务层负责加密）。"""

    in_page_enabled: bool = True
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: Optional[int] = None
    smtp_username: str = ""
    smtp_credential: Optional[str] = None  # 明文，保存时加密
    email_to: str = ""


@dataclass
class MaskedConfig:
    """对外展示用的配置视图，凭证以掩码呈现（需求 7.6/8.6）。"""

    status_threshold: int
    reminder_thresholds: List[int]
    in_page_enabled: bool
    email_enabled: bool
    smtp_host: str
    smtp_port: Optional[int]
    smtp_username: str
    smtp_credential_mask: str
    email_to: str
    cloudflare_token_mask: str


class ConfigService:
    def __init__(self, store: DataStore, encryption_key: Optional[str] = None):
        self._store = store
        self._key = encryption_key
        self._config = AppConfig()

    def load(self) -> Result:
        result = self._store.load_config()
        if result.is_err:
            return result
        self._config = result.value
        return Result.ok(self._config)

    @property
    def config(self) -> AppConfig:
        return self._config

    # ----------------------------------------------------------------- #
    # 读取（掩码视图）
    # ----------------------------------------------------------------- #
    def get_config(self) -> MaskedConfig:
        """返回配置的掩码视图，绝不回显凭证明文（需求 7.6/8.6）。"""
        c = self._config
        smtp_plain = crypto.decrypt_credential(
            c.notification.smtp_credential_encrypted, self._key
        )
        cf_plain = crypto.decrypt_credential(c.cloudflare_token_encrypted, self._key)
        return MaskedConfig(
            status_threshold=c.status_threshold,
            reminder_thresholds=list(c.reminder_thresholds),
            in_page_enabled=c.notification.in_page_enabled,
            email_enabled=c.notification.email_enabled,
            smtp_host=c.notification.smtp_host,
            smtp_port=c.notification.smtp_port,
            smtp_username=c.notification.smtp_username,
            smtp_credential_mask=crypto.mask_credential(smtp_plain),
            email_to=c.notification.email_to,
            cloudflare_token_mask=crypto.mask_credential(cf_plain),
        )

    # ----------------------------------------------------------------- #
    # 更新
    # ----------------------------------------------------------------- #
    def update_reminder_threshold(self, value: object) -> Result:
        """更新状态计算阈值 status_threshold（需求 2.4/7.3）。"""
        if not _is_int_in_range(value, STATUS_THRESHOLD_MIN, STATUS_THRESHOLD_MAX):
            return Result.fail(
                ErrorCode.INVALID_THRESHOLD,
                f"状态阈值必须是 {STATUS_THRESHOLD_MIN}–{STATUS_THRESHOLD_MAX} 之间的整数",
            )
        new_config = _clone(self._config)
        new_config.status_threshold = int(value)
        return self._persist(new_config)

    def update_reminder_thresholds(self, values: object) -> Result:
        """更新提醒发送阈值列表（需求 3.1/3.7）。"""
        err = _validate_threshold_list(values)
        if err is not None:
            return Result.fail(ErrorCode.INVALID_THRESHOLD, err)
        new_config = _clone(self._config)
        new_config.reminder_thresholds = [int(v) for v in values]
        return self._persist(new_config)

    def update_notification_settings(self, settings: NotificationInput) -> Result:
        """更新通知设置；启用邮件时校验完整性（需求 4.4/7.4）。"""
        if settings.email_enabled:
            has_stored_credential = (
                self._config.notification.smtp_credential_encrypted is not None
            )
            missing = _missing_email_fields(settings, has_stored_credential)
            if missing:
                return Result.fail(
                    ErrorCode.INVALID_NOTIFICATION,
                    f"启用邮件提醒需提供完整配置，缺失：{', '.join(missing)}",
                )
        new_config = _clone(self._config)
        # 凭据加密存储；未提供新凭据则保留原有加密凭据。
        if settings.smtp_credential:
            cred_enc = crypto.encrypt_credential(settings.smtp_credential, self._key)
        else:
            cred_enc = self._config.notification.smtp_credential_encrypted
        new_config.notification = NotificationSettings(
            in_page_enabled=settings.in_page_enabled,
            email_enabled=settings.email_enabled,
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_username=settings.smtp_username,
            smtp_credential_encrypted=cred_enc,
            email_to=settings.email_to,
        )
        return self._persist(new_config)

    def update_cloudflare_credentials(self, token: str) -> Result:
        """加密存储 Cloudflare 凭证（需求 7.6）。"""
        if not token:
            return Result.fail(ErrorCode.INVALID_NOTIFICATION, "Cloudflare 凭证不能为空")
        new_config = _clone(self._config)
        new_config.cloudflare_token_encrypted = crypto.encrypt_credential(token, self._key)
        return self._persist(new_config)

    # ----------------------------------------------------------------- #
    # 内部
    # ----------------------------------------------------------------- #
    def _persist(self, new_config: AppConfig) -> Result:
        """持久化新配置；写失败则保留旧配置不变（需求 7.5）。"""
        write = self._store.save_config(new_config)
        if write.is_err:
            return write  # 旧配置 self._config 未被替换
        self._config = new_config
        return Result.ok(self.get_config())


# --------------------------------------------------------------------------- #
# 校验辅助
# --------------------------------------------------------------------------- #
def _is_int_in_range(value: object, lo: int, hi: int) -> bool:
    # bool 是 int 的子类，需显式排除。
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return lo <= value <= hi


def _validate_threshold_list(values: object) -> Optional[str]:
    """返回 None 表示合法，否则返回错误原因（需求 3.1/3.7）。"""
    if not isinstance(values, (list, tuple)):
        return "提醒阈值必须是整数列表"
    if not (1 <= len(values) <= REMINDER_THRESHOLDS_MAX_COUNT):
        return f"提醒阈值数量必须为 1–{REMINDER_THRESHOLDS_MAX_COUNT} 个"
    seen = set()
    for v in values:
        if not _is_int_in_range(v, REMINDER_THRESHOLD_MIN, REMINDER_THRESHOLD_MAX):
            return (
                f"每个提醒阈值必须是 {REMINDER_THRESHOLD_MIN}–{REMINDER_THRESHOLD_MAX} 之间的整数"
            )
        if v in seen:
            return "提醒阈值不能重复"
        seen.add(v)
    return None


def _missing_email_fields(s: NotificationInput, has_stored_credential: bool = False) -> List[str]:
    """返回缺失的邮件配置字段（需求 4.4）。"""
    missing = []
    if not s.smtp_host:
        missing.append("服务器地址")
    if not s.smtp_port:
        missing.append("端口")
    if not s.smtp_username:
        missing.append("发件账户")
    # 认证凭据：已有加密凭据或本次提供明文均可视为存在。
    if not s.smtp_credential and not has_stored_credential:
        missing.append("认证凭据")
    return missing


def _clone(config: AppConfig) -> AppConfig:
    return AppConfig(
        status_threshold=config.status_threshold,
        reminder_thresholds=list(config.reminder_thresholds),
        notification=NotificationSettings(
            in_page_enabled=config.notification.in_page_enabled,
            email_enabled=config.notification.email_enabled,
            smtp_host=config.notification.smtp_host,
            smtp_port=config.notification.smtp_port,
            smtp_username=config.notification.smtp_username,
            smtp_credential_encrypted=config.notification.smtp_credential_encrypted,
            email_to=config.notification.email_to,
        ),
        cloudflare_token_encrypted=config.cloudflare_token_encrypted,
    )
