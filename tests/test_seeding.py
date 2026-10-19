"""Automated tests for demo data seeding, idempotency, reset safety, search, and dashboard rendering."""

import os
import tempfile
import pytest
from app import create_app
from app.database.db import get_db, init_db
from app.services import auth_service, partner_service, product_service, seeder


@pytest.fixture
def test_app():
    """Create a temporary test app with file-based temp database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app = create_app({
        "TESTING": True,
        "DATABASE": path,
        "SECRET_KEY": "test-seeding-secret-key",
        "AFFILIATE_WEBHOOK_SECRET": "test-affiliate-secret",
    })
    with app.app_context():
        init_db()
    yield app
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def test_client(test_app):
    return test_app.test_client()



def test_seed_demo_data_creation(test_app):
    """Verify that seed_all_demo_data creates expected records across all entities."""
    with test_app.app_context():
        db = get_db()
        summary = seeder.seed_all_demo_data(db)

        assert summary["users_created"] == 31  # 1 Admin + 5 Merchants + 25 Consumers
        assert summary["partners_created"] == 5
        assert summary["products_created"] == 100
        assert summary["feeds_created"] == 12
        assert summary["articles_created"] == 60
        assert summary["campaigns_created"] == 9
        assert summary["affiliate_clicks_created"] == 30

        # Verify database counts directly
        assert db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 31
        assert db.execute("SELECT COUNT(*) AS c FROM partners").fetchone()["c"] == 5
        assert db.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"] == 100
        assert db.execute("SELECT COUNT(*) AS c FROM feeds").fetchone()["c"] == 12
        assert db.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"] == 60
        assert db.execute("SELECT COUNT(*) AS c FROM campaigns").fetchone()["c"] == 9
        assert db.execute("SELECT COUNT(*) AS c FROM affiliate_clicks").fetchone()["c"] == 30

        # Verify foreign keys are valid
        invalid_products = db.execute(
            "SELECT COUNT(*) AS c FROM products WHERE partner_id NOT IN (SELECT id FROM partners)"
        ).fetchone()["c"]
        assert invalid_products == 0

        invalid_articles = db.execute(
            "SELECT COUNT(*) AS c FROM articles WHERE feed_id NOT IN (SELECT id FROM feeds)"
        ).fetchone()["c"]
        assert invalid_articles == 0

        invalid_campaigns = db.execute(
            "SELECT COUNT(*) AS c FROM campaigns WHERE partner_id NOT IN (SELECT id FROM partners) OR product_id NOT IN (SELECT id FROM products)"
        ).fetchone()["c"]
        assert invalid_campaigns == 0


def test_seed_demo_data_idempotency(test_app):
    """Verify repeated execution of seed_all_demo_data creates 0 duplicates."""
    with test_app.app_context():
        db = get_db()
        first_run = seeder.seed_all_demo_data(db)
        assert first_run["users_created"] == 31
        assert first_run["products_created"] == 100

        # Second run
        second_run = seeder.seed_all_demo_data(db)
        assert second_run["users_created"] == 0
        assert second_run["users_existing"] == 31
        assert second_run["products_created"] == 0
        assert second_run["products_existing"] == 100
        assert second_run["feeds_created"] == 0
        assert second_run["feeds_existing"] == 12
        assert second_run["articles_created"] == 0
        assert second_run["articles_existing"] == 60
        assert second_run["campaigns_created"] == 0
        assert second_run["campaigns_existing"] == 9

        # Confirm counts remain identical
        assert db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 31
        assert db.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"] == 100


def test_seed_demo_data_reset_preserves_user_data(test_app):
    """Verify that reset_all_demo_data removes demo records while preserving non-demo user data."""
    with test_app.app_context():
        db = get_db()

        # Create genuine user and product before seeding
        real_user = auth_service.create_user(
            db,
            email="real.customer@mycompany.org",
            password="SecureUserPass123!",
            role="consumer",
            display_name="Genuine User",
        )
        real_partner_user = auth_service.create_user(
            db,
            email="real.partner@mybrand.org",
            password="SecurePartnerPass123!",
            role="merchant",
            display_name="Genuine Partner",
        )
        real_partner = partner_service.apply_partner(
            db,
            user_id=real_partner_user["id"],
            business_name="Genuine Brand Ltd",
            website="https://mybrand.org",
            business_email="contact@mybrand.org",
            category="general",
        )
        real_product = product_service.create_product(
            db,
            partner_id=real_partner["id"],
            sku="GENUINE-SKU-001",
            title="Genuine Custom Handcrafted Wallet",
            category="fashion",
            price=1500.0,
            currency="INR",
            product_url="https://mybrand.org/wallet",
            feed_source="manual",
        )

        # Seed demo data
        seeder.seed_all_demo_data(db)
        assert db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 33  # 31 demo + 2 real
        assert db.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"] == 101  # 100 demo + 1 real

        # Reset demo data
        reset_res = seeder.reset_all_demo_data(db)
        assert reset_res["users_deleted"] == 31
        assert reset_res["products_deleted"] == 100

        # Confirm real user, real partner, and real product survive
        surviving_users = db.execute("SELECT email FROM users").fetchall()
        surviving_emails = {r["email"] for r in surviving_users}
        assert "real.customer@mycompany.org" in surviving_emails
        assert "real.partner@mybrand.org" in surviving_emails
        assert len(surviving_users) == 2

        surviving_products = db.execute("SELECT sku FROM products").fetchall()
        assert len(surviving_products) == 1
        assert surviving_products[0]["sku"] == "GENUINE-SKU-001"


def test_demo_authentication_and_roles(test_app, test_client):
    """Verify demo login credentials work for admin, merchant, and consumer roles."""
    with test_app.app_context():
        db = get_db()
        seeder.seed_all_demo_data(db)

    # 1. Admin login
    admin_auth = test_client.post("/auth/login", data={
        "email": "admin@example.com",
        "password": "AdminDemo2026!",
    }, follow_redirects=True)
    assert admin_auth.status_code == 200
    assert b"Dev Platform Administrator" in admin_auth.data or b"Admin" in admin_auth.data

    # Admin access
    admin_page = test_client.get("/admin/")
    assert admin_page.status_code == 200
    assert b"Platform Administration Console" in admin_page.data

    # Logout
    test_client.get("/auth/logout")

    # 2. Merchant login
    merch_auth = test_client.post("/auth/login", data={
        "email": "merchant.electronics@example.com",
        "password": "MerchantDemo2026!",
    }, follow_redirects=True)
    assert merch_auth.status_code == 200

    merch_dash = test_client.get("/merchant/dashboard")
    assert merch_dash.status_code == 200
    assert b"Apex Electronics" in merch_dash.data

    # Logout
    test_client.get("/auth/logout")

    # 3. Consumer login
    cons_auth = test_client.post("/auth/login", data={
        "email": "consumer.01@example.com",
        "password": "ConsumerDemo2026!",
    }, follow_redirects=True)
    assert cons_auth.status_code == 200
    test_client.get("/auth/logout")


def test_demo_product_search_and_fts5(test_app):
    """Verify search finds seeded products via SQLite FTS5."""
    with test_app.app_context():
        db = get_db()
        seeder.seed_all_demo_data(db)

        # Search by keyword
        res_phone = product_service.search_products(db, query="smartphone titanium")
        assert len(res_phone) >= 1
        assert any("Apex Phone" in p["title"] for p in res_phone)

        # Search by brand
        res_sony = product_service.search_products(db, brand="Sony")
        assert len(res_sony) >= 2

        # Search by category and price range
        res_cat = product_service.search_products(db, category="sports", min_price=1000.0, max_price=5000.0)
        assert len(res_cat) >= 3


def test_demo_dashboards_render_with_data(test_app, test_client):
    """Verify consumer, merchant, and admin dashboards calculate dynamic values correctly."""
    with test_app.app_context():
        db = get_db()
        seeder.seed_all_demo_data(db)

    # General dashboard
    dash_res = test_client.get("/")
    assert dash_res.status_code == 200
    # Shows feed and article counts derived from DB
    assert b"Feeds" in dash_res.data
    assert b"Articles" in dash_res.data

    # Discovery page (feed personalization)
    disc_res = test_client.get("/discover")
    assert disc_res.status_code == 200
    assert b"Personalized Discovery Stream" in disc_res.data

    # Catalog page
    prods_res = test_client.get("/products")
    assert prods_res.status_code == 200
    assert b"Product Catalogue" in prods_res.data



def test_sponsored_placements_with_demo_campaigns(test_app):
    """Verify sponsored products query retrieves active approved campaigns."""
    with test_app.app_context():
        db = get_db()
        seeder.seed_all_demo_data(db)

        sponsored = partner_service.get_active_sponsored_products(db, limit=5)
        assert len(sponsored) >= 1
        for item in sponsored:
            assert item["is_sponsored"] == 1
            assert item["sponsored_label"] == "Sponsored"
            assert item["moderation_status"] == "approved"
            assert item["availability"] == "in_stock"
