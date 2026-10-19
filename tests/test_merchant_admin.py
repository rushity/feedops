"""Tests for Merchant and Admin Workflows, Isolation, and Moderation."""

import pytest
from app.database.db import get_db
from app.services import auth_service, partner_service, product_service


def test_merchant_application_and_approval(app):
    """Verify partner application submission and admin approval with audit logging."""
    with app.app_context():
        db = get_db()
        merchant_user = auth_service.create_user(db, "merch1@example.com", "pass12345", role="merchant", is_verified=True)
        admin_user = auth_service.create_user(db, "admin1@example.com", "pass12345", role="admin", is_verified=True)

        # Apply as partner
        partner = partner_service.apply_partner(
            db,
            user_id=merchant_user["id"],
            business_name="Acme Electronics Ltd",
            website="https://acme.example.com",
            business_email="contact@acme.example.com",
            category="electronics",
        )
        assert partner["status"] == "submitted"
        partner_id = partner["id"]

        # Admin approves partner
        updated = partner_service.update_partner_status(
            db,
            partner_id=partner_id,
            status="approved",
            admin_user_id=admin_user["id"],
        )
        assert updated["status"] == "approved"

        # Verify audit log was recorded
        log = db.execute(
            "SELECT * FROM audit_logs WHERE target_type = 'partner' AND target_id = ?",
            (partner_id,),
        ).fetchone()
        assert log is not None
        assert log["user_id"] == admin_user["id"]
        assert "approved" in log["details"].lower()


def test_merchant_data_isolation(app):
    """Verify that merchant data queries are strictly isolated between partners."""
    with app.app_context():
        db = get_db()
        m1 = auth_service.create_user(db, "isolated1@example.com", "pass12345", role="merchant", is_verified=True)
        m2 = auth_service.create_user(db, "isolated2@example.com", "pass12345", role="merchant", is_verified=True)

        p1 = partner_service.apply_partner(db, m1["id"], "Partner One", "https://p1.com", "p1@p1.com", "electronics")
        p2 = partner_service.apply_partner(db, m2["id"], "Partner Two", "https://p2.com", "p2@p2.com", "fashion")

        product_service.create_product(
            db, partner_id=p1["id"], sku="P1-SKU", title="P1 Item",
            description="", category="electronics", brand="B1", price=10.0, product_url="https://p1.com/1"
        )
        product_service.create_product(
            db, partner_id=p2["id"], sku="P2-SKU", title="P2 Item",
            description="", category="fashion", brand="B2", price=20.0, product_url="https://p2.com/2"
        )

        # Query isolated to partner 1
        p1_products = product_service.search_products(db, partner_id=p1["id"])
        assert len(p1_products) == 1
        assert p1_products[0]["sku"] == "P1-SKU"
        assert not any(p["sku"] == "P2-SKU" for p in p1_products)

        # Query isolated to partner 2
        p2_products = product_service.search_products(db, partner_id=p2["id"])
        assert len(p2_products) == 1
        assert p2_products[0]["sku"] == "P2-SKU"
        assert not any(p["sku"] == "P1-SKU" for p in p2_products)


def test_admin_product_moderation(client, app):
    """Verify admin moderation of products."""
    with app.app_context():
        db = get_db()
        admin_user = auth_service.create_user(db, "admin_mod@example.com", "pass12345", role="admin", is_verified=True)
        prod = product_service.create_product(
            db, partner_id=None, sku="SKU-MOD", title="Pending Product",
            description="", category="general", price=50.0, product_url="https://example.com/mod",
            moderation_status="pending"
        )
        prod_id = prod["id"]

    # Log in as admin
    client.post("/auth/login", data={"email": "admin_mod@example.com", "password": "pass12345"})

    # Moderate product to approved
    res = client.post(f"/admin/products/{prod_id}/moderate", data={"status": "approved"}, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        db = get_db()
        updated_prod = product_service.get_product_by_id(db, prod_id)
        assert updated_prod["moderation_status"] == "approved"


def test_merchant_campaign_lifecycle_and_isolation(app, client):
    """Verify campaign creation, data isolation, admin moderation, and sponsored retrieval."""
    with app.app_context():
        db = get_db()
        m1 = auth_service.create_user(db, "camp_m1@example.com", "pass12345", role="merchant", is_verified=True)
        m2 = auth_service.create_user(db, "camp_m2@example.com", "pass12345", role="merchant", is_verified=True)
        admin = auth_service.create_user(db, "camp_admin@example.com", "pass12345", role="admin", is_verified=True)

        p1 = partner_service.apply_partner(db, m1["id"], "M1 Brands", "https://m1.com", "m1@m1.com", "tech")
        p2 = partner_service.apply_partner(db, m2["id"], "M2 Brands", "https://m2.com", "m2@m2.com", "tech")
        partner_service.update_partner_status(db, p1["id"], "approved")
        partner_service.update_partner_status(db, p2["id"], "approved")

        prod1 = product_service.create_product(
            db, partner_id=p1["id"], sku="PROD-1", title="Flagship ANC Headphones",
            category="tech", price=199.99, product_url="https://m1.com/p1"
        )
        prod2 = product_service.create_product(
            db, partner_id=p2["id"], sku="PROD-2", title="Competitor Earbuds",
            category="tech", price=99.99, product_url="https://m2.com/p2"
        )

        # 1. Partner 1 cannot create campaign for Partner 2's product (merchant isolation)
        with pytest.raises(PermissionError):
            partner_service.create_campaign(
                db, partner_id=p1["id"], product_id=prod2["id"], title="Sneaky Campaign",
                start_date="2026-10-01", end_date="2026-10-31"
            )

        # 2. Date validation (start_date > end_date)
        with pytest.raises(ValueError):
            partner_service.create_campaign(
                db, partner_id=p1["id"], product_id=prod1["id"], title="Invalid Dates",
                start_date="2026-10-31", end_date="2026-10-01"
            )

        # 3. Successful campaign creation by Partner 1
        camp = partner_service.create_campaign(
            db, partner_id=p1["id"], product_id=prod1["id"], title="Autumn Launch",
            start_date="2026-10-01", end_date="2026-11-01", daily_budget=20.0, total_budget=200.0
        )
        assert camp["status"] == "pending"
        camp_id = camp["id"]

        # 4. Admin approves campaign
        partner_service.update_campaign_status(db, camp_id, status="active", admin_user_id=admin["id"])
        approved_camp = partner_service.get_campaign_by_id(db, camp_id)
        assert approved_camp["status"] == "active"

        # 5. Active sponsored products retrieval
        sponsored = partner_service.get_active_sponsored_products(db, limit=5)
        assert any(item["id"] == prod1["id"] for item in sponsored)
        assert all(item["is_sponsored"] == 1 for item in sponsored)

        # 6. Merchant pauses and resumes campaign
        partner_service.update_campaign_status(db, camp_id, status="paused", partner_id=p1["id"])
        paused_camp = partner_service.get_campaign_by_id(db, camp_id)
        assert paused_camp["status"] == "paused"

        partner_service.update_campaign_status(db, camp_id, status="active", partner_id=p1["id"])
        resumed_camp = partner_service.get_campaign_by_id(db, camp_id)
        assert resumed_camp["status"] == "active"

        # 7. Admin suspends campaign
        partner_service.update_campaign_status(
            db, camp_id, status="suspended", rejection_reason="Terms violation", admin_user_id=admin["id"]
        )
        suspended_camp = partner_service.get_campaign_by_id(db, camp_id)
        assert suspended_camp["status"] == "suspended"

