"""End-to-End Integration Tests for Discovery, Merchant, Admin, and Privacy Workflows."""

import json
import pytest
from app.database.db import get_db
from app.services import auth_service, partner_service, product_service, privacy_service


def test_full_consumer_journey(client, app):
    """E2E Journey: Register -> Set Preferences -> Browse Discovery Feed -> Save Item -> Dismiss Item -> Click Outbound."""
    # 1. Register Consumer
    reg_res = client.post(
        "/auth/register",
        data={
            "email": "e2e_consumer@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "display_name": "E2E Explorer",
            "age_confirmed": "1",
            "terms_accepted": "1",
            "consent_personalization": "1",
            "consent_marketing": "1",
        },
        follow_redirects=True,
    )
    assert reg_res.status_code == 200
    assert "Preferences" in reg_res.data.decode("utf-8")

    # 2. Configure Consumer Preferences
    pref_res = client.post(
        "/auth/preferences",
        data={
            "interests": ["electronics", "home"],
            "budget_min": "50",
            "budget_max": "1200",
            "preferred_brands": "Sony, Dyson",
            "currency": "USD",
            "consent_personalization": "1",
        },
        follow_redirects=True,
    )
    assert pref_res.status_code == 200
    assert "saved" in pref_res.data.decode("utf-8").lower()

    # Seed products into the database
    with app.app_context():
        db = get_db()
        p1 = product_service.create_product(
            db, sku="E2E-1", title="Sony Bravia 55 inch OLED 4K", category="electronics",
            brand="Sony", price=999.0, product_url="https://store.example.com/bravia"
        )
        p2 = product_service.create_product(
            db, sku="E2E-2", title="Dyson V12 Cordless Vacuum", category="home",
            brand="Dyson", price=599.0, product_url="https://store.example.com/dyson"
        )
        p3 = product_service.create_product(
            db, sku="E2E-3", title="Unwanted Item", category="automotive",
            brand="Generic", price=45.0, product_url="https://store.example.com/unwanted"
        )
        p1_id, p2_id, p3_id = p1["id"], p2["id"], p3["id"]

    # 3. View Personalized Discovery Feed
    feed_res = client.get("/discover")
    assert feed_res.status_code == 200
    feed_html = feed_res.data.decode("utf-8")
    assert "Sony Bravia" in feed_html
    assert "Matches your Electronics interest" in feed_html

    # 4. Save Product to Shortlist
    save_res = client.post(f"/products/{p1_id}/save", follow_redirects=True)
    assert save_res.status_code == 200
    assert "shortlist" in save_res.data.decode("utf-8").lower()

    saved_res = client.get("/saved")
    assert saved_res.status_code == 200
    assert "Sony Bravia" in saved_res.data.decode("utf-8")

    # 5. Dismiss Unwanted Product
    dismiss_res = client.post(f"/products/{p3_id}/dismiss", follow_redirects=True)
    assert dismiss_res.status_code == 200

    # Verify dismissed product disappears from feed
    feed_after_dismiss = client.get("/discover").data.decode("utf-8")
    assert "Unwanted Item" not in feed_after_dismiss

    # 6. Click Outbound Referral (Tracked Click)
    click_res = client.get(f"/products/{p1_id}/click")
    assert click_res.status_code == 302
    assert "click_id=" in click_res.location
    assert "utm_source=feedops_discovery" in click_res.location


def test_full_merchant_journey(client, app):
    """E2E Journey: Register Merchant -> Apply as Partner -> Dashboard -> Ingest CSV Catalogue -> Inspect Products."""
    # 1. Register Merchant User
    client.post(
        "/auth/register",
        data={
            "email": "retailer@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "display_name": "Retailer Partner",
            "role": "merchant",
            "age_confirmed": "1",
            "terms_accepted": "1",
        },
        follow_redirects=True,
    )

    # 2. Submit Partner Application
    apply_res = client.post(
        "/merchant/apply",
        data={
            "business_name": "Nordic Retail Hub",
            "website": "https://nordicretail.example.com",
            "business_email": "partners@nordicretail.example.com",
            "category": "fashion",
            "partner_type": "merchant",
        },
        follow_redirects=True,
    )
    assert apply_res.status_code == 200
    assert "submitted" in apply_res.data.decode("utf-8").lower()

    with app.app_context():
        db = get_db()
        partner = db.execute("SELECT * FROM partners WHERE business_name = 'Nordic Retail Hub'").fetchone()
        assert partner is not None
        # Simulate admin approval
        db.execute("UPDATE partners SET status = 'approved' WHERE id = ?", (partner["id"],))
        db.commit()

    # 3. Access Merchant Dashboard
    dash_res = client.get("/merchant/dashboard")
    assert dash_res.status_code == 200
    assert "Nordic Retail Hub" in dash_res.data.decode("utf-8")

    # 4. Ingest Catalogue via CSV
    sample_csv = (
        "sku,title,category,price,currency,availability,brand,product_url\n"
        "NORD-101,Nordic Wool Sweater,fashion,120.00,USD,in_stock,NordicWear,https://nordicretail.example.com/sweater\n"
        "NORD-102,Waterproof Parka,fashion,240.00,USD,in_stock,NordicWear,https://nordicretail.example.com/parka\n"
    )
    upload_res = client.post(
        "/merchant/upload",
        data={"csv_text": sample_csv},
        follow_redirects=True,
    )
    assert upload_res.status_code == 200
    assert "Catalogue imported successfully" in upload_res.data.decode("utf-8")

    # 5. Check Merchant Products List
    prod_res = client.get("/merchant/products")
    assert prod_res.status_code == 200
    assert "Nordic Wool Sweater" in prod_res.data.decode("utf-8")
    assert "Waterproof Parka" in prod_res.data.decode("utf-8")


def test_full_admin_and_governance_journey(client, app):
    """E2E Journey: Admin logs in -> Approves Partner -> Moderates Products -> Views Audit Logs."""
    with app.app_context():
        db = get_db()
        admin = auth_service.create_user(db, "superadmin@example.com", "Password123!", role="admin", is_verified=True)
        partner_user = auth_service.create_user(db, "pending_partner@example.com", "Password123!", role="merchant", is_verified=True)
        partner = partner_service.apply_partner(db, partner_user["id"], "Pending Brand LLC", "https://pending.example.com", "hi@pending.com", "electronics")
        partner_id = partner["id"]

    # 1. Admin Login
    client.post("/auth/login", data={"email": "superadmin@example.com", "password": "Password123!"})

    # 2. View Admin Dashboard
    dash_res = client.get("/admin/")
    assert dash_res.status_code == 200
    assert "Platform Administration" in dash_res.data.decode("utf-8")

    # 3. Approve Partner
    approve_res = client.post(f"/admin/partners/{partner_id}/action", data={"action": "approved"}, follow_redirects=True)
    assert approve_res.status_code == 200

    # 4. View Audit Log
    audit_res = client.get("/admin/audit-logs")
    assert audit_res.status_code == 200
    assert "partner_status_change" in audit_res.data.decode("utf-8")


def test_privacy_and_data_export_flow(client, app):
    """E2E Journey: Update notification settings -> Revoke consent -> Export data (JSON) -> Delete account."""
    with app.app_context():
        db = get_db()
        user = auth_service.create_user(db, "privacy_e2e@example.com", "Password123!", is_verified=True)
        user_id = user["id"]

    client.post("/auth/login", data={"email": "privacy_e2e@example.com", "password": "Password123!"})

    # 1. Update Notification Preferences
    notif_res = client.post(
        "/privacy/notifications",
        data={
            "price_drop_alerts": "1",
            "email_alerts": "1",
            "digest_frequency": "daily",
            "quiet_hours_start": "23:00",
            "quiet_hours_end": "07:00",
        },
        follow_redirects=True,
    )
    assert notif_res.status_code == 200
    assert "Notification settings updated" in notif_res.data.decode("utf-8")

    # 2. Revoke Consent for Marketing
    consent_res = client.post(
        "/privacy/consents",
        data={"consent_type": "marketing", "granted": "0"},
        follow_redirects=True,
    )
    assert consent_res.status_code == 200
    assert "revoked" in consent_res.data.decode("utf-8").lower()

    # 3. Export Machine-Readable Personal Data
    export_res = client.get("/privacy/export")
    assert export_res.status_code == 200
    payload = json.loads(export_res.data.decode("utf-8"))
    assert payload["user_profile"]["email"] == "privacy_e2e@example.com"
    assert "notification_settings" in payload

    # 4. Delete Account (Right to Erasure)
    del_res = client.post("/privacy/delete-account", data={"confirmation": "DELETE MY ACCOUNT"}, follow_redirects=True)
    assert del_res.status_code == 200
    assert "permanently deleted" in del_res.data.decode("utf-8")

    with app.app_context():
        db = get_db()
        assert auth_service.get_user_by_id(db, user_id) is None


def test_e2e_campaign_sponsored_flow(client, app):
    """E2E Journey: Merchant creates ad campaign -> Admin approves -> Appears on Discovery with Sponsored label."""
    with app.app_context():
        db = get_db()
        # Create merchant and admin users
        m_user = auth_service.create_user(db, "sponsor_merch@example.com", "Password123!", role="merchant", is_verified=True)
        a_user = auth_service.create_user(db, "sponsor_admin@example.com", "Password123!", role="admin", is_verified=True)

        partner = partner_service.apply_partner(db, m_user["id"], "Sonic Audio", "https://sonicaudio.com", "sonic@audio.com", "audio")
        partner_service.update_partner_status(db, partner["id"], "approved")

        prod = product_service.create_product(
            db, partner_id=partner["id"], sku="SONIC-1", title="Sonic Studio Reference Monitor",
            category="electronics", brand="Sonic", price=299.99, product_url="https://sonicaudio.com/p1"
        )
        p_id = prod["id"]

    # 1. Log in as merchant and submit campaign
    client.post("/auth/login", data={"email": "sponsor_merch@example.com", "password": "Password123!"})
    new_camp_res = client.post(
        "/merchant/campaigns/new",
        data={
            "title": "Sonic Summer Showcase",
            "product_id": str(p_id),
            "start_date": "2026-10-01",
            "end_date": "2026-11-30",
            "daily_budget": "15.00",
            "total_budget": "150.00",
        },
        follow_redirects=True
    )
    assert new_camp_res.status_code == 200
    assert "Sonic Summer Showcase" in new_camp_res.data.decode("utf-8")

    # 2. Log in as admin and approve campaign
    client.get("/auth/logout")
    client.post("/auth/login", data={"email": "sponsor_admin@example.com", "password": "Password123!"})

    with app.app_context():
        db = get_db()
        camp = db.execute("SELECT id FROM campaigns WHERE title = 'Sonic Summer Showcase'").fetchone()
        camp_id = camp["id"]

    appr_res = client.post(f"/admin/campaigns/{camp_id}/approve", follow_redirects=True)
    assert appr_res.status_code == 200
    assert "approved" in appr_res.data.decode("utf-8").lower()

    # 3. View Discovery Feed as consumer and verify sponsored placement
    client.get("/auth/logout")
    feed_res = client.get("/discover")
    assert feed_res.status_code == 200
    feed_text = feed_res.data.decode("utf-8")
    assert "Sonic Studio Reference Monitor" in feed_text
    assert "Sponsored" in feed_text

