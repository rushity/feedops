"""Partner and Merchant Service.

Handles merchant registration, business profile verification, application statuses,
product catalogue submissions, and isolation guarantees.
"""

from datetime import datetime, timezone


def apply_partner(db, user_id: int, business_name: str, website: str,
                  business_email: str, category: str, partner_type: str = "merchant"):
    """Submit a new partner application."""
    business_name = (business_name or "").strip()
    business_email = (business_email or "").strip().lower()
    website = (website or "").strip()

    if not business_name:
        raise ValueError("Business name is required.")
    if not business_email or "@" not in business_email:
        raise ValueError("A valid business email is required.")

    # Check if already applied
    existing = get_partner_by_user_id(db, user_id)
    if existing:
        db.execute(
            """UPDATE partners SET
                   business_name = ?, website = ?, business_email = ?,
                   category = ?, partner_type = ?, status = 'submitted', updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (business_name, website, business_email, category, partner_type, existing["id"]),
        )
        db.commit()
        return get_partner_by_id(db, existing["id"])

    cur = db.execute(
        """INSERT INTO partners (user_id, business_name, website, business_email, category, partner_type, status)
           VALUES (?, ?, ?, ?, ?, ?, 'submitted')""",
        (user_id, business_name, website, business_email, category, partner_type),
    )
    db.commit()
    return get_partner_by_id(db, cur.lastrowid)


def get_partner_by_id(db, partner_id: int):
    """Retrieve partner by partner ID."""
    row = db.execute("SELECT * FROM partners WHERE id = ?", (partner_id,)).fetchone()
    return dict(row) if row else None


def get_partner_by_user_id(db, user_id: int):
    """Retrieve partner record by associated user ID."""
    row = db.execute("SELECT * FROM partners WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def list_partners(db, status: str = None):
    """List partners filtered by status."""
    if status:
        rows = db.execute("SELECT * FROM partners WHERE status = ? ORDER BY id DESC", (status,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM partners ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def update_partner_status(db, partner_id: int, status: str, rejection_reason: str = None, admin_user_id: int = None):
    """Admin action to update partner application status."""
    allowed = {"submitted", "needs_changes", "approved", "suspended", "rejected"}
    if status not in allowed:
        raise ValueError(f"Invalid partner status. Allowed: {allowed}")

    db.execute(
        """UPDATE partners SET status = ?, rejection_reason = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (status, rejection_reason, partner_id),
    )

    # Log audit event
    if admin_user_id:
        db.execute(
            """INSERT INTO audit_logs (user_id, action, target_type, target_id, details)
               VALUES (?, 'partner_status_change', 'partner', ?, ?)""",
            (admin_user_id, partner_id, f"Changed status to {status}. Reason: {rejection_reason or 'None'}"),
        )
    db.commit()
    return get_partner_by_id(db, partner_id)


def get_merchant_metrics(db, partner_id: int):
    """Retrieve operational metrics for a specific merchant."""
    products_row = db.execute(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN availability = 'in_stock' THEN 1 ELSE 0 END) AS in_stock FROM products WHERE partner_id = ?",
        (partner_id,),
    ).fetchone()

    clicks_row = db.execute(
        "SELECT COUNT(*) AS total_clicks FROM affiliate_clicks WHERE partner_id = ?",
        (partner_id,),
    ).fetchone()

    imports_row = db.execute(
        "SELECT COUNT(*) AS total_jobs FROM feed_import_jobs WHERE partner_id = ?",
        (partner_id,),
    ).fetchone()

    return {
        "total_products": int(products_row["total"] or 0) if products_row else 0,
        "in_stock_products": int(products_row["in_stock"] or 0) if products_row else 0,
        "total_clicks": int(clicks_row["total_clicks"] or 0) if clicks_row else 0,
        "total_import_jobs": int(imports_row["total_jobs"] or 0) if imports_row else 0,
    }


def record_import_job(db, partner_id: int, filename: str, status: str, items_total: int,
                      items_imported: int, items_skipped: int, error_log: str = None):
    """Log an import job result."""
    cur = db.execute(
        """INSERT INTO feed_import_jobs (partner_id, filename, status, items_total, items_imported, items_skipped, error_log)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (partner_id, filename, status, items_total, items_imported, items_skipped, error_log),
    )
    db.commit()
    return cur.lastrowid


def list_import_jobs(db, partner_id: int = None, limit: int = 20):
    """List recent import jobs."""
    if partner_id:
        rows = db.execute(
            "SELECT * FROM feed_import_jobs WHERE partner_id = ? ORDER BY id DESC LIMIT ?",
            (partner_id, limit),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM feed_import_jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Merchant Campaigns & Sponsored Placements
# ---------------------------------------------------------------------------

def create_campaign(db, partner_id: int, product_id: int, title: str,
                    start_date: str, end_date: str, daily_budget: float = 0.0,
                    total_budget: float = 0.0, max_impressions_per_user: int = 3):
    """Create a new merchant campaign with data isolation enforcement."""
    title = (title or "").strip()
    if not title:
        raise ValueError("Campaign title is required.")

    # 1. Enforce merchant data isolation: verify product belongs to this partner
    product = db.execute("SELECT id, partner_id, moderation_status FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        raise ValueError("Product not found.")
    if product["partner_id"] != partner_id:
        raise PermissionError("Unauthorized: Product does not belong to your merchant account.")

    # 2. Validate dates
    if not start_date or not end_date:
        raise ValueError("Start date and end date are required.")
    if start_date > end_date:
        raise ValueError("Start date must be before or equal to end date.")

    # 3. Validate budgets
    try:
        d_budget = max(0.0, float(daily_budget or 0.0))
        t_budget = max(0.0, float(total_budget or 0.0))
    except (ValueError, TypeError):
        raise ValueError("Invalid budget value.")

    cur = db.execute(
        """INSERT INTO campaigns (
               partner_id, product_id, title, daily_budget, total_budget,
               start_date, end_date, max_impressions_per_user, status
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (partner_id, product_id, title, d_budget, t_budget, start_date, end_date, max(1, int(max_impressions_per_user or 3))),
    )
    db.commit()
    return get_campaign_by_id(db, cur.lastrowid, partner_id=partner_id)


def get_campaign_by_id(db, campaign_id: int, partner_id: int = None):
    """Retrieve campaign, strictly enforcing merchant isolation if partner_id is provided."""
    sql = """
        SELECT c.*, p.title AS product_title, p.price AS product_price, p.image_url AS product_image,
               pt.business_name AS partner_name
        FROM campaigns c
        JOIN products p ON c.product_id = p.id
        JOIN partners pt ON c.partner_id = pt.id
        WHERE c.id = ?
    """
    params = [campaign_id]
    if partner_id is not None:
        sql += " AND c.partner_id = ?"
        params.append(partner_id)

    row = db.execute(sql, tuple(params)).fetchone()
    return dict(row) if row else None


def list_campaigns(db, partner_id: int = None, status: str = None):
    """List campaigns with optional partner isolation and status filter."""
    sql = """
        SELECT c.*, p.title AS product_title, p.price AS product_price, p.image_url AS product_image,
               pt.business_name AS partner_name
        FROM campaigns c
        JOIN products p ON c.product_id = p.id
        JOIN partners pt ON c.partner_id = pt.id
    """
    where = []
    params = []
    if partner_id is not None:
        where.append("c.partner_id = ?")
        params.append(partner_id)
    if status:
        where.append("c.status = ?")
        params.append(status)

    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY c.id DESC"

    rows = db.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def update_campaign_status(db, campaign_id: int, status: str, rejection_reason: str = None,
                           admin_user_id: int = None, partner_id: int = None):
    """Update campaign status (admin approval/rejection or merchant pause/resume)."""
    allowed = {"pending", "active", "paused", "rejected", "completed", "suspended"}
    if status not in allowed:
        raise ValueError(f"Invalid campaign status. Allowed: {allowed}")

    sql = "UPDATE campaigns SET status = ?, rejection_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
    params = [status, rejection_reason, campaign_id]
    if partner_id is not None:
        sql += " AND partner_id = ?"
        params.append(partner_id)

    db.execute(sql, tuple(params))

    # Audit logging for admin actions
    if admin_user_id:
        db.execute(
            """INSERT INTO audit_logs (user_id, action, target_type, target_id, details)
               VALUES (?, 'campaign_status_change', 'campaign', ?, ?)""",
            (admin_user_id, campaign_id, f"Changed campaign status to {status}. Reason: {rejection_reason or 'None'}"),
        )
    db.commit()
    return get_campaign_by_id(db, campaign_id)


def get_active_sponsored_products(db, limit: int = 3, user_id: int = None):
    """Retrieve active approved sponsored products strictly separated from organic ranking."""
    sql = """
        SELECT p.*, pt.business_name AS partner_name, c.id AS campaign_id, c.title AS campaign_title,
               c.max_impressions_per_user
        FROM campaigns c
        JOIN products p ON c.product_id = p.id
        JOIN partners pt ON c.partner_id = pt.id
        WHERE c.status = 'active'
          AND date(c.start_date) <= date('now')
          AND date(c.end_date) >= date('now')
          AND p.moderation_status = 'approved'
          AND p.availability = 'in_stock'
    """
    rows = db.execute(sql).fetchall()
    results = []

    # Exclude products dismissed by user and enforce frequency capping
    dismissed_ids = set()
    if user_id:
        from app.services import product_service
        dismissed_ids = product_service.get_dismissed_product_ids(db, user_id)

    for r in rows:
        if r["id"] in dismissed_ids:
            continue
        item = dict(r)
        item["is_sponsored"] = 1
        item["sponsored_label"] = "Sponsored"
        results.append(item)
        if len(results) >= limit:
            break

    return results

