"""域名列表、仪表盘与 CRUD 路由（需求 1、4.1、8）。"""
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

from ..channels import InPageChannel
from ..domain_service import DomainInput
from ..models import DomainStatus
from ..status import status_remaining_days
from .auth_views import login_required

domains_bp = Blueprint("domains", __name__)

# 状态 -> 视觉标识 CSS 类（需求 8.5，三者互不相同）。
STATUS_BADGE = {
    DomainStatus.ACTIVE: "badge-active",
    DomainStatus.EXPIRING: "badge-expiring",
    DomainStatus.EXPIRED: "badge-expired",
}


def _domain_service():
    return current_app.config["DOMAIN_SERVICE"]


def _today():
    return current_app.config["CLOCK"]().date()


def _view_rows(records):
    """组装模板所需的展示行（含剩余天数与徽标类）。"""
    today = _today()
    rows = []
    for r in records:
        rd = status_remaining_days(r.expiration_date, today)
        rows.append(
            {
                "id": r.id,
                "name": r.name,
                "expiration_date": r.expiration_date,
                "remaining_days": rd,
                "status": r.status.value,
                "badge": STATUS_BADGE[r.status],
                "source": r.source.value,
                "notes": r.notes,
                "missing_expiration": r.expiration_date is None,
            }
        )
    return rows


@domains_bp.route("/")
@login_required
def dashboard():
    """仪表盘：集中展示 Expiring/Expired 域名（需求 4.1）。"""
    service = _domain_service()
    service.load()
    alerts = InPageChannel.collect_alerts(service.list_domains())
    return render_template("dashboard.html", rows=_view_rows(alerts))


@domains_bp.route("/domains")
@login_required
def list_domains():
    """域名列表：按状态筛选、按剩余天数升序、状态视觉区分（需求 8.1/8.3/8.4/8.5）。"""
    service = _domain_service()
    service.load()
    status_param = request.args.get("status")
    status_filter = None
    if status_param in {s.value for s in DomainStatus}:
        status_filter = DomainStatus(status_param)
    records = service.list_domains(status_filter=status_filter)
    return render_template(
        "domains.html",
        rows=_view_rows(records),
        current_filter=status_param or "",
        statuses=[s.value for s in DomainStatus],
    )


@domains_bp.route("/domains", methods=["POST"])
@login_required
def create_domain():
    service = _domain_service()
    service.load()
    data = DomainInput(
        name=request.form.get("name", "").strip(),
        expiration_date=request.form.get("expiration_date", "").strip(),
        platform=request.form.get("platform", "").strip(),
        notes=request.form.get("notes", "").strip(),
    )
    result = service.create_domain(data)
    if result.is_err:
        # 保留用户输入并展示可读错误（需求 8.8）。
        flash(result.error.message, "error")
        return (
            render_template("domain_form.html", mode="create", form=request.form),
            400,
        )
    flash("域名已创建", "info")
    return redirect(url_for("domains.list_domains"))


@domains_bp.route("/domains/new")
@login_required
def new_domain_form():
    return render_template("domain_form.html", mode="create", form={})


@domains_bp.route("/domains/<domain_id>/edit")
@login_required
def edit_domain_form(domain_id):
    service = _domain_service()
    service.load()
    result = service.get_domain(domain_id)
    if result.is_err:
        flash(result.error.message, "error")
        return redirect(url_for("domains.list_domains"))
    r = result.value
    form = {
        "name": r.name,
        "expiration_date": r.expiration_date.isoformat() if r.expiration_date else "",
        "platform": r.platform,
        "notes": r.notes,
    }
    return render_template(
        "domain_form.html", mode="edit", form=form, domain_id=domain_id
    )


@domains_bp.route("/domains/<domain_id>", methods=["POST"])
@login_required
def update_domain(domain_id):
    service = _domain_service()
    service.load()
    data = DomainInput(
        name=request.form.get("name", "").strip(),
        expiration_date=request.form.get("expiration_date", "").strip(),
        platform=request.form.get("platform", "").strip(),
        notes=request.form.get("notes", "").strip(),
    )
    result = service.update_domain(domain_id, data)
    if result.is_err:
        flash(result.error.message, "error")
        return (
            render_template(
                "domain_form.html", mode="edit", form=request.form, domain_id=domain_id
            ),
            400,
        )
    flash("域名已更新", "info")
    return redirect(url_for("domains.list_domains"))


@domains_bp.route("/domains/<domain_id>/delete", methods=["POST"])
@login_required
def delete_domain(domain_id):
    service = _domain_service()
    service.load()
    result = service.delete_domain(domain_id)
    if result.is_err:
        flash(result.error.message, "error")
    else:
        flash("域名已删除", "info")
    return redirect(url_for("domains.list_domains"))
