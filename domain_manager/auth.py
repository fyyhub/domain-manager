"""Auth_Service：认证、会话与暴力破解锁定（需求 9）。

设计要点：
- 口令以 Werkzeug PBKDF2 加盐哈希存储，不可逆且不回显（需求 9.7）。
- 登录成功建立会话，自最后活动起 30 分钟空闲超时（需求 9.3/9.5）。
- 登出立即使会话失效（需求 9.6）。
- 认证失败返回统一文案，不区分用户名/密码（需求 9.4）。
- 同一账户 15 分钟滑动窗口内失败达 5 次，锁定 15 分钟（需求 9.8）。

时间相关逻辑均以可注入的 now 实现，便于属性测试。
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from .models import ErrorCode, Result, Session, User
from .store import DataStore

# 会话空闲超时（需求 9.3/9.5）。
SESSION_IDLE_TIMEOUT = timedelta(minutes=30)
# 锁定参数（需求 9.8）。
LOCKOUT_WINDOW = timedelta(minutes=15)
LOCKOUT_DURATION = timedelta(minutes=15)
LOCKOUT_THRESHOLD = 5

# PBKDF2 迭代次数。生产环境使用 Werkzeug 默认的高强度值（不显式指定），
# 测试可通过环境变量 DM_PBKDF2_ITERATIONS 降低以加速属性测试；
# 安全属性（加盐、不可逆、可校验）不依赖具体迭代次数。
_PBKDF2_ITERATIONS = os.environ.get("DM_PBKDF2_ITERATIONS")

# 统一认证失败文案（需求 9.4，不区分用户名/密码）。
_AUTH_FAILED_MSG = "用户名或密码错误"


# --------------------------------------------------------------------------- #
# 纯函数
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """以 PBKDF2 加盐方式哈希口令（需求 9.7）。"""
    if _PBKDF2_ITERATIONS:
        method = f"pbkdf2:sha256:{int(_PBKDF2_ITERATIONS)}"
    else:
        method = "pbkdf2:sha256"
    return generate_password_hash(password, method=method)


def verify_password(password: str, hashed: str) -> bool:
    """校验明文口令与哈希是否匹配（需求 9.7）。"""
    if not hashed:
        return False
    try:
        return check_password_hash(hashed, password)
    except (ValueError, TypeError):
        return False


def is_lockout_triggered(failures_in_window: int) -> bool:
    """窗口内失败次数是否达到锁定阈值（需求 9.8）。"""
    return failures_in_window >= LOCKOUT_THRESHOLD


def count_failures_in_window(
    failed_attempts, now: datetime, window: timedelta = LOCKOUT_WINDOW
) -> int:
    """统计 now 之前 window 时间窗内的失败次数。"""
    cutoff = now - window
    return sum(1 for t in failed_attempts if t is not None and t > cutoff)


# --------------------------------------------------------------------------- #
# Auth_Service
# --------------------------------------------------------------------------- #
class AuthService:
    def __init__(self, store: DataStore, clock: Optional[Callable[[], datetime]] = None):
        self._store = store
        self._clock = clock or datetime.now
        self._sessions: Dict[str, Session] = {}
        self._user: Optional[User] = None

    # ----------------------------------------------------------------- #
    # 账户初始化
    # ----------------------------------------------------------------- #
    def load(self) -> Result:
        result = self._store.load_user()
        if result.is_err:
            return result
        self._user = result.value
        return Result.ok(self._user)

    def ensure_admin(self, username: str, password: str) -> Result:
        """首次启动创建默认管理员账户（若尚不存在）。"""
        load = self.load()
        if load.is_err:
            return load
        if self._user is not None:
            return Result.ok(self._user)
        user = User(username=username, password_hash=hash_password(password))
        write = self._store.save_user(user)
        if write.is_err:
            return write
        self._user = user
        return Result.ok(user)

    @property
    def user(self) -> Optional[User]:
        return self._user

    # ----------------------------------------------------------------- #
    # 锁定判定
    # ----------------------------------------------------------------- #
    def is_locked(self, username: str, now: Optional[datetime] = None) -> bool:
        """账户是否处于锁定期内（需求 9.8）。"""
        now = now or self._clock()
        if self._user is None or self._user.username != username:
            return False
        locked_until = self._user.locked_until
        return locked_until is not None and now < locked_until

    def record_failed_attempt(self, username: str, now: Optional[datetime] = None) -> Result:
        """记录一次失败尝试，必要时触发锁定（需求 9.8）。"""
        now = now or self._clock()
        if self._user is None or self._user.username != username:
            return Result.ok(None)
        # 仅保留窗口内的失败时间戳。
        cutoff = now - LOCKOUT_WINDOW
        self._user.failed_attempts = [
            t for t in self._user.failed_attempts if t is not None and t > cutoff
        ]
        self._user.failed_attempts.append(now)
        if is_lockout_triggered(count_failures_in_window(self._user.failed_attempts, now)):
            self._user.locked_until = now + LOCKOUT_DURATION
        self._store.save_user(self._user)
        return Result.ok(None)

    def _reset_failures(self, now: datetime) -> None:
        if self._user is not None:
            self._user.failed_attempts = []
            self._user.locked_until = None
            self._store.save_user(self._user)

    # ----------------------------------------------------------------- #
    # 登录 / 校验 / 登出
    # ----------------------------------------------------------------- #
    def login(self, username: str, password: str, now: Optional[datetime] = None) -> Result:
        """登录（需求 9.3/9.4/9.8）。"""
        now = now or self._clock()
        # 锁定优先：锁定期内直接拒绝（需求 9.8）。
        if self.is_locked(username, now):
            return Result.fail(ErrorCode.ACCOUNT_LOCKED, "账户已被临时锁定，请稍后再试")

        ok = (
            self._user is not None
            and self._user.username == username
            and verify_password(password, self._user.password_hash)
        )
        if not ok:
            self.record_failed_attempt(username, now)
            # 若本次失败触发锁定，仍返回统一认证失败文案以不泄露账户状态细节。
            return Result.fail(ErrorCode.AUTH_FAILED, _AUTH_FAILED_MSG)

        # 成功：清空失败计数并建立会话。
        self._reset_failures(now)
        session = Session(session_id=str(uuid.uuid4()), username=username, last_active_at=now)
        self._sessions[session.session_id] = session
        return Result.ok(session)

    def validate_session(self, session_id: str, now: Optional[datetime] = None) -> Result:
        """校验会话有效性并刷新最后活动时间（需求 9.1/9.2/9.5）。"""
        now = now or self._clock()
        session = self._sessions.get(session_id)
        if session is None:
            return Result.fail(ErrorCode.SESSION_INVALID, "会话无效或已失效")
        # 空闲超时判定（需求 9.5）。
        if now - session.last_active_at > SESSION_IDLE_TIMEOUT:
            self._sessions.pop(session_id, None)
            return Result.fail(ErrorCode.SESSION_INVALID, "会话已超时，请重新登录")
        # 刷新最后活动时间。
        session.last_active_at = now
        return Result.ok(session)

    def logout(self, session_id: str) -> Result:
        """登出，立即使会话失效（需求 9.6）。"""
        self._sessions.pop(session_id, None)
        return Result.ok(None)
