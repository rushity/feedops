"""Privacy, Compliance, and Notification Management Service.

Implements:
- Notification preferences (channels, frequency, quiet hours, pause/unsub)
- Price drop and availability event tracking
- Consent history and granular consent revocation
- GDPR / DPDP Article 20 user data export (JSON)
- Right to erasure / account deletion execution
"""

from datetime import datetime, timezone
import json


def get_notification_preferences(db, user_id: int):
    """Retrieve user notification settings."""
    row = db.execute("SELECT * FROM notification_preferences WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return {
            "email_alerts": 1,
            "price_drop_alerts": 1,
            "availability_alerts": 1,
            "digest_frequency": "daily",
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00",
            "is_paused": 0,
        }
    return dict(row)


def update_notification_preferences(db, user_id: int, email_alerts: bool, price_drop_alerts: bool,
                                    availability_alerts: bool, digest_frequency: str = "daily",
                                    quiet_hours_start: str = "22:00", quiet_hours_end: str = "08:00",
                                    is_paused: bool = False):
    """Save user notification settings."""
    db.execute(
        """INSERT INTO notification_preferences (
               user_id, email_alerts, price_drop_alerts, availability_alerts,
               digest_frequency, quiet_hours_start, quiet_hours_end, is_paused, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(user_id) DO UPDATE SET
               email_alerts = excluded.email_alerts,
               price_drop_alerts = excluded.price_drop_alerts,
               availability_alerts = excluded.availability_alerts,
               digest_frequency = excluded.digest_frequency,
               quiet_hours_start = excluded.quiet_hours_start,
               quiet_hours_end = excluded.quiet_hours_end,
               is_paused = excluded.is_paused,
               updated_at = CURRENT_TIMESTAMP""",
        (
            user_id, 1 if email_alerts else 0, 1 if price_drop_alerts else 0,
            1 if availability_alerts else 0, digest_frequency,
            quiet_hours_start, quiet_hours_end, 1 if is_paused else 0
        ),
    )
    db.commit()
    return get_notification_preferences(db, user_id)


def list_user_notifications(db, user_id: int, limit: int = 50):
    """Retrieve user notification feed."""
    rows = db.execute(
        """SELECT n.*, p.title as product_title, p.price as current_price
           FROM notification_events n
           LEFT JOIN products p ON n.product_id = p.id
           WHERE n.user_id = ?
           ORDER BY n.id DESC LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_notification_read(db, user_id: int, notification_id: int):
    """Mark a notification as read."""
    db.execute("UPDATE notification_events SET is_read = 1 WHERE id = ? AND user_id = ?", (notification_id, user_id))
    db.commit()


def trigger_price_drop_alert(db, product_id: int, old_price: float, new_price: float):
    """Notify all users who saved this product when price drops."""
    if new_price >= old_price:
        return 0

    product_row = db.execute("SELECT title FROM products WHERE id = ?", (product_id,)).fetchone()
    title = product_row["title"] if product_row else "Product"

    # Find users who saved this product and have price drop alerts enabled
    sql = """
        SELECT s.user_id
        FROM saved_items s
        JOIN notification_preferences np ON s.user_id = np.user_id
        WHERE s.product_id = ? AND np.price_drop_alerts = 1 AND np.is_paused = 0
    """
    users = db.execute(sql, (product_id,)).fetchall()
    count = 0
    drop_pct = round(((old_price - new_price) / old_price) * 100)

    for u in users:
        # Check if identical alert already exists to prevent duplicates on repeated runs
        existing_alert = db.execute(
            """SELECT id FROM notification_events
               WHERE user_id = ? AND product_id = ? AND event_type = 'price_drop'
               AND title = ?""",
            (u["user_id"], product_id, f"Price Drop: {drop_pct}% off on {title[:40]}"),
        ).fetchone()
        if existing_alert:
            continue

        db.execute(
            """INSERT INTO notification_events (user_id, product_id, event_type, title, message)
               VALUES (?, ?, 'price_drop', ?, ?)""",
            (
                u["user_id"],
                product_id,
                f"Price Drop: {drop_pct}% off on {title[:40]}",
                f"Price dropped from ${old_price:,.2f} to ${new_price:,.2f}!",
            ),
        )
        count += 1
    db.commit()
    return count


def export_user_data(db, user_id: int):
    """Generate GDPR / DPDP compliant complete data export dictionary for a user."""
    user = db.execute("SELECT id, email, display_name, phone, role, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return None

    preferences = db.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)).fetchone()
    consents = db.execute("SELECT * FROM consent_records WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
    saved = db.execute(
        """SELECT s.note, s.created_at, p.sku, p.title, p.price, p.category, p.product_url
           FROM saved_items s
           JOIN products p ON s.product_id = p.id
           WHERE s.user_id = ?""",
        (user_id,),
    ).fetchall()
    feedback = db.execute("SELECT * FROM user_feedback WHERE user_id = ?", (user_id,)).fetchall()
    notifications = db.execute("SELECT * FROM notification_events WHERE user_id = ?", (user_id,)).fetchall()
    notification_settings = db.execute("SELECT * FROM notification_preferences WHERE user_id = ?", (user_id,)).fetchone()

    return {
        "export_metadata": {
            "format_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "subject": "Personal Data Portability Export (GDPR / DPDP aligned)",
        },
        "user_profile": dict(user),
        "preferences": dict(preferences) if preferences else {},
        "consent_history": [dict(c) for c in consents],
        "saved_products": [dict(s) for s in saved],
        "feedback_and_dismissals": [dict(f) for f in feedback],
        "notification_settings": dict(notification_settings) if notification_settings else {},
        "notifications_history": [dict(n) for n in notifications],
    }


def execute_account_deletion(db, user_id: int):
    """Execute complete right-to-erasure account deletion."""
    # Delete cascade handles: user_preferences, consent_records, saved_items,
    # user_feedback, notification_preferences, notification_events, data_requests
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.execute(
        """INSERT INTO audit_logs (user_id, action, target_type, target_id, details)
           VALUES (NULL, 'account_erasure', 'user', ?, 'Executed account deletion under Right to Erasure.')""",
        (user_id,),
    )
    db.commit()
    return True
