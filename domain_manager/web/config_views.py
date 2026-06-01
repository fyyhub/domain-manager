"""配置页与 Cloudflare 同步路由（需求 5.6、7、8.6、8.7）。"""
from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from ..config_service import NotificationInput
from .auth_views import login_required

config_bp = Blueprint("config", __name__)


def _config_service():
    return current_app.config["CONFIG_SERVICE"]


@config_bp.route("/config")
@login_required
def config_page():
    """配置页：凭证以掩码呈现，绝不回显明文（需求 8.6）。"""
    svc = _config_service()
    svc.load()
    return render_template("config.html", config=svc.get_config())


@config_bp.route("/config", methods=["POST"])
@login_required
def save_config():
    svc = _config_service()
    svc.load()
    section = request.form.get("section", "")

    if section == "thresholds":
        # 状态阈值。
        try:
            status_threshold = int(request.form.get("status_threshold", ""))
        except ValueError:
            flash("状态阈值必须是整数", "error")
            return redirect(url_for("config.config_page"))
        res = svc.update_reminder_threshold(status_threshold)
        if res.is_err:
            flash(res.error.message, "error")
            return redirect(url_for("config.config_page"))
        # 提醒阈值列表（逗号分隔）。
        raw = request.form.get("reminder_thresholds", "")
        try:
            thresholds = [int(x.strip()) for x in raw.split(",") if x.strip()]
        except ValueError:
            flash("提醒阈值必须是以逗号分隔的整数", "error")
            return redirect(url_for("config.config_page"))
        res2 = svc.update_reminder_thresholds(thresholds)
        if res2.is_err:
            flash(res2.error.message, "error")
            return redirect(url_for("config.config_page"))
        flash("阈值配置已保存", "info")

    elif section == "notification":
        port_raw = request.form.get("smtp_port", "").strip()
        port = int(port_raw) if port_raw.isdigit() else None
        settings_in = NotificationInput(
            in_page_enabled=request.form.get("in_page_enabled") == "on",
            email_enabled=request.form.get("email_enabled") == "on",
            smtp_host=request.form.get("smtp_host", "").strip(),
            smtp_port=port,
            smtp_username=request.form.get("smtp_username", "").strip(),
            smtp_credential=request.form.get("smtp_credential", "").strip() or None,
            email_to=request.form.get("email_to", "").strip(),
        )
        res = svc.update_notification_settings(settings_in)
        if res.is_err:
            flash(res.error.message, "error")
        else:
            flash("通知配置已保存", "info")

    elif section == "cloudflare":
        token = request.form.get("cloudflare_token", "").strip()
        if token:
            res = svc.update_cloudflare_credentials(token)
            if res.is_err:
                flash(res.error.message, "error")
            else:
                flash("Cloudflare 凭证已保存", "info")
        else:
            flash("未提供 Cloudflare 凭证", "warning")

    return redirect(url_for("config.config_page"))


@config_bp.route("/cloudflare/sync", methods=["POST"])
@login_required
def cloudflare_sync():
    """触发 Cloudflare 同步并展示结果摘要（需求 5.6/8.7）。"""
    sync = current_app.config.get("CLOUDFLARE_SYNC")
    if sync is None:
        flash("尚未配置 Cloudflare 凭证，无法同步", "warning")
        return redirect(url_for("config.config_page"))
    result = sync.sync()
    if result.is_err:
        flash(f"同步失败：{result.error.message}", "error")
    else:
        summary = result.value
        flash(
            f"同步完成：新建 {summary.created} 条，更新 {summary.updated} 条",
            "info",
        )
    return redirect(url_for("domains.list_domains"))
