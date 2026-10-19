"""Admin Portal Routes for platform moderation, partner review, and governance."""

from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from app.database.db import get_db
from app.services import auth_service, partner_service, product_service

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
@auth_service.roles_accepted("admin")
def require_admin():
    """Ensure all admin endpoints require admin role."""
    pass


@admin_bp.route("/", endpoint="index")
@admin_bp.route("/dashboard", endpoint="dashboard")
def index():
    """Admin Executive Dashboard."""
    db = get_db()

    user_count = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    partner_count = db.execute("SELECT COUNT(*) AS c FROM partners").fetchone()["c"]
    pending_partners = db.execute("SELECT COUNT(*) AS c FROM partners WHERE status = 'submitted'").fetchone()["c"]
    product_count = db.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    clicks_count = db.execute("SELECT COUNT(*) AS c FROM affiliate_clicks").fetchone()["c"]

    recent_partners = partner_service.list_partners(db)[:5]
    recent_audit = db.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 10").fetchall()

    return render_template(
        "admin_dashboard.html",
        user_count=user_count,
        partner_count=partner_count,
        pending_partners=pending_partners,
        product_count=product_count,
        clicks_count=clicks_count,
        recent_partners=recent_partners,
        recent_audit=[dict(a) for a in recent_audit],
    )


@admin_bp.route("/partners")
def partners():
    """Manage partner applications."""
    db = get_db()
    status_filter = request.args.get("status")
    all_partners = partner_service.list_partners(db, status=status_filter or None)
    return render_template("admin_partners.html", partners=all_partners, status_filter=status_filter)


@admin_bp.route("/partners/<int:partner_id>/action", methods=["POST"])
def partner_action(partner_id: int):
    """Approve, reject, or suspend a partner."""
    db = get_db()
    action = request.form.get("action")  # 'approved', 'rejected', 'suspended'
    reason = request.form.get("reason", "").strip()

    try:
        partner_service.update_partner_status(
            db,
            partner_id=partner_id,
            status=action,
            rejection_reason=reason or None,
            admin_user_id=session["user_id"],
        )
        flash(f"Partner status updated to '{action}'.", "success")
    except Exception as exc:
        flash(f"Failed to update partner: {exc}", "error")

    return redirect(url_for("admin.partners"))


@admin_bp.route("/products")
def products():
    """Product moderation list."""
    db = get_db()
    items = product_service.list_products(db, limit=50, moderation_status=None)
    return render_template("admin_products.html", products=items)


@admin_bp.route("/products/<int:product_id>/moderate", methods=["POST"])
def moderate_product(product_id: int):
    """Update product moderation status."""
    db = get_db()
    status = request.form.get("status", "approved")  # 'approved', 'rejected'
    db.execute("UPDATE products SET moderation_status = ? WHERE id = ?", (status, product_id))
    db.execute(
        """INSERT INTO audit_logs (user_id, action, target_type, target_id, details)
           VALUES (?, 'product_moderation', 'product', ?, ?)""",
        (session["user_id"], product_id, f"Set moderation status to {status}"),
    )
    db.commit()
    flash(f"Product {product_id} moderation updated to {status}.", "success")
    return redirect(url_for("admin.products"))


@admin_bp.route("/stale-catalogues")
def stale_catalogues():
    """Monitor stale products not updated in over 30 days."""
    db = get_db()
    # Find products where last_updated_at is older than 30 days or NULL
    sql = """
        SELECT p.*, pt.business_name AS partner_name
        FROM products p
        LEFT JOIN partners pt ON p.partner_id = pt.id
        WHERE p.last_updated_at <= datetime('now', '-30 days')
        ORDER BY p.last_updated_at ASC
        LIMIT 50
    """
    stale_items = [dict(r) for r in db.execute(sql).fetchall()]
    return render_template("admin_stale.html", stale_products=stale_items)


@admin_bp.route("/users")
def users():
    """User account governance."""
    db = get_db()
    all_users = db.execute("SELECT id, email, role, display_name, status, is_verified, created_at FROM users ORDER BY id DESC LIMIT 100").fetchall()
    return render_template("admin_users.html", users=[dict(u) for u in all_users])


@admin_bp.route("/users/<int:user_id>/toggle-status", methods=["POST"])
def toggle_user_status(user_id: int):
    """Toggle user active / suspended status."""
    db = get_db()
    user = auth_service.get_user_by_id(db, user_id)
    if not user:
        abort(404)
    new_status = "suspended" if user["status"] == "active" else "active"
    db.execute("UPDATE users SET status = ? WHERE id = ?", (new_status, user_id))
    db.execute(
        """INSERT INTO audit_logs (user_id, action, target_type, target_id, details)
           VALUES (?, 'user_status_change', 'user', ?, ?)""",
        (session["user_id"], user_id, f"Changed status from {user['status']} to {new_status}"),
    )
    db.commit()
    flash(f"User {user['email']} status changed to {new_status}.", "info")
    return redirect(url_for("admin.users"))


@admin_bp.route("/audit-logs")
def audit_logs():
    """View system audit trail."""
    db = get_db()
    logs = db.execute(
        """SELECT a.*, u.email as user_email
           FROM audit_logs a
           LEFT JOIN users u ON a.user_id = u.id
           ORDER BY a.id DESC LIMIT 100"""
    ).fetchall()
    return render_template("admin_audit.html", logs=[dict(l) for l in logs])



@admin_bp.route("/campaigns")
def campaigns():
    """List and review all partner advertising campaigns."""
    db = get_db()
    status = request.args.get("status")
    all_campaigns = partner_service.list_campaigns(db, status=status)
    return render_template("admin_campaigns.html", campaigns=all_campaigns, current_status=status)


@admin_bp.route("/campaigns/<int:campaign_id>/approve", methods=["POST"])
def approve_campaign(campaign_id: int):
    """Approve a merchant campaign."""
    db = get_db()
    partner_service.update_campaign_status(
        db, campaign_id, status="active", admin_user_id=session["user_id"]
    )
    flash(f"Campaign {campaign_id} has been approved and activated.", "success")
    return redirect(url_for("admin.campaigns"))


@admin_bp.route("/campaigns/<int:campaign_id>/reject", methods=["POST"])
def reject_campaign(campaign_id: int):
    """Reject a merchant campaign."""
    db = get_db()
    reason = request.form.get("reason", "Violates platform placement guidelines")
    partner_service.update_campaign_status(
        db, campaign_id, status="rejected", rejection_reason=reason, admin_user_id=session["user_id"]
    )
    flash(f"Campaign {campaign_id} rejected.", "info")
    return redirect(url_for("admin.campaigns"))


@admin_bp.route("/campaigns/<int:campaign_id>/suspend", methods=["POST"])
def suspend_campaign(campaign_id: int):
    """Suspend a merchant campaign."""
    db = get_db()
    reason = request.form.get("reason", "Suspended by administrator")
    partner_service.update_campaign_status(
        db, campaign_id, status="suspended", rejection_reason=reason, admin_user_id=session["user_id"]
    )
    flash(f"Campaign {campaign_id} suspended.", "warning")
    return redirect(url_for("admin.campaigns"))

