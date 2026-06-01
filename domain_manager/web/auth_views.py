"""认证路由与 login_required 装饰器（需求 9）。"""
from __future__ import annotations

from functools import wraps

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from ..models import ErrorCode

auth_bp = Blueprint("auth", __name__)

SESSION_KEY = "dm_session_id"


def login_required(view):
    """保护视图：未认证或会话失效则重定向到登录页（需求 9.1/9.2/9.5）。"""

    @wraps(view)
    def wrapped(*args, **kwargs):
        auth = current_app.config["AUTH_SERVICE"]
        sid = session.get(SESSION_KEY)
        result = auth.validate_session(sid) if sid else None
        if not sid or result is None or result.is_err:
            session.pop(SESSION_KEY, None)
            flash("请先登录", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    auth = current_app.config["AUTH_SERVICE"]
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        result = auth.login(username, password)
        if result.is_ok:
            session[SESSION_KEY] = result.value.session_id
            next_url = request.args.get("next") or url_for("domains.dashboard")
            return redirect(next_url)
        # 统一失败/锁定提示（需求 9.4/9.8）。
        if result.error.code == ErrorCode.ACCOUNT_LOCKED:
            flash(result.error.message, "error")
        else:
            flash("用户名或密码错误", "error")
    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    auth = current_app.config["AUTH_SERVICE"]
    sid = session.pop(SESSION_KEY, None)
    if sid:
        auth.logout(sid)  # 立即失效（需求 9.6）
    flash("已登出", "info")
    return redirect(url_for("auth.login"))
