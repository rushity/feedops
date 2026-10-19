"""Tests for Privacy, Consent, Notifications, Data Export, and Account Erasure."""

import json
import pytest
from app.database.db import get_db
from app.services import auth_service, product_service, privacy_service


def test_notification_preferences_and_price_drop_alerts(app):
    """Verify notification preference updates and price drop alert generation for shortlisted items."""
    with app.app_context():
        db = get_db()
        user = auth_service.create_user(db, "alertuser@example.com", "pass12345", is_verified=True)
        user_id = user["id"]

        # Configure notification preferences
        privacy_service.update_notification_preferences(
            db,
            user_id=user_id,
            email_alerts=True,
            price_drop_alerts=True,
            availability_alerts=True,
            digest_frequency="daily",
        )

        # Create product and save it for this user
        prod = product_service.create_product(
            db, partner_id=None, sku="SKU-ALERT", title="Smart 4K TV",
            description="", category="electronics", price=800.0, product_url="https://example.com/tv"
        )
        product_service.save_product(db, user_id, prod["id"])

        # Trigger price drop: price fell from $800 to $650
        alerts_sent = privacy_service.trigger_price_drop_alert(db, prod["id"], old_price=800.0, new_price=650.0)
        assert alerts_sent == 1

        # Check notification in user's inbox
        inbox = privacy_service.list_user_notifications(db, user_id)
        assert len(inbox) == 1
        assert "Price Drop" in inbox[0]["title"]
        assert "$650.00" in inbox[0]["message"]


def test_user_data_export(client, app):
    """Verify GDPR / DPDP compliant data export JSON generation."""
    with app.app_context():
        db = get_db()
        user = auth_service.create_user(db, "exportuser@example.com", "pass12345", is_verified=True)
        user_id = user["id"]

        auth_service.update_user_preferences(db, user_id, interests=["home"], budget_min=50, budget_max=500)
        auth_service.record_consent(db, user_id, "personalization", True)

    client.post("/auth/login", data={"email": "exportuser@example.com", "password": "pass12345"})
    res = client.get("/privacy/export")
    assert res.status_code == 200
    assert res.mimetype == "application/json"

    data = json.loads(res.data.decode("utf-8"))
    assert "user_profile" in data
    assert data["user_profile"]["email"] == "exportuser@example.com"
    assert "preferences" in data
    assert "consent_history" in data
    assert "saved_products" in data


def test_account_deletion_right_to_erasure(client, app):
    """Verify account erasure deletes user records and cascades."""
    with app.app_context():
        db = get_db()
        user = auth_service.create_user(db, "deleteuser@example.com", "pass12345", is_verified=True)
        user_id = user["id"]

    client.post("/auth/login", data={"email": "deleteuser@example.com", "password": "pass12345"})

    # Reject if wrong confirmation text
    res_bad = client.post("/privacy/delete-account", data={"confirmation": "wrong text"})
    assert "DELETE MY ACCOUNT" in res_bad.data.decode("utf-8")

    # Confirm deletion
    res_ok = client.post("/privacy/delete-account", data={"confirmation": "DELETE MY ACCOUNT"}, follow_redirects=True)
    assert res_ok.status_code == 200
    assert "permanently deleted" in res_ok.data.decode("utf-8")

    with app.app_context():
        db = get_db()
        assert auth_service.get_user_by_id(db, user_id) is None
        # Check audit log contains erasure entry
        log = db.execute("SELECT * FROM audit_logs WHERE action = 'account_erasure'").fetchone()
        assert log is not None
