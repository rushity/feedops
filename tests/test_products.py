"""Tests for Product Catalogue, Ingestion, Filtering, and Tracking."""

import pytest
from app.database.db import get_db
from app.services import product_service, auth_service


def test_product_creation_and_filters(app):
    """Verify product catalogue creation and multi-filtering."""
    with app.app_context():
        db = get_db()
        p1 = product_service.create_product(
            db, partner_id=None, sku="SKU-1", title="Sony WH-1000XM5 Headphones",
            description="Active noise cancelling wireless headphones", category="electronics",
            brand="Sony", price=349.99, availability="in_stock", product_url="https://example.com/p1"
        )
        p2 = product_service.create_product(
            db, partner_id=None, sku="SKU-2", title="Nike Air Zoom Pegasus",
            description="Running shoes for athletes", category="sports",
            brand="Nike", price=129.99, availability="in_stock", product_url="https://example.com/p2"
        )
        p3 = product_service.create_product(
            db, partner_id=None, sku="SKU-3", title="KitchenAid Stand Mixer",
            description="Professional home kitchen appliance", category="home",
            brand="KitchenAid", price=449.99, availability="out_of_stock", product_url="https://example.com/p3"
        )

        assert p1["id"] is not None
        assert p2["id"] is not None

        # Filter by category
        el_items = product_service.search_products(db, category="electronics")
        assert any(item["sku"] == "SKU-1" for item in el_items)
        assert not any(item["sku"] == "SKU-2" for item in el_items)

        # Filter by price range
        budget_items = product_service.search_products(db, max_price=200.0)
        assert any(item["sku"] == "SKU-2" for item in budget_items)
        assert not any(item["sku"] == "SKU-1" for item in budget_items)

        # Filter by availability
        avail_items = product_service.search_products(db, availability="out_of_stock")
        assert any(item["sku"] == "SKU-3" for item in avail_items)

        # Filter by query
        query_items = product_service.search_products(db, query="Noise cancelling")
        assert any(item["sku"] == "SKU-1" for item in query_items)


def test_saved_products_and_dismissal(app):
    """Verify shortlist saving and product dismissal."""
    with app.app_context():
        db = get_db()
        user = auth_service.create_user(db, "saveuser@example.com", "pass12345", is_verified=True)
        user_id = user["id"]

        prod = product_service.create_product(
            db, partner_id=None, sku="SKU-SAVE", title="MacBook Air M3",
            description="Apple laptop", category="electronics", brand="Apple",
            price=1099.0, product_url="https://example.com/macbook"
        )
        prod_id = prod["id"]

        # Check not saved initially
        assert not product_service.is_product_saved(db, user_id, prod_id)

        # Save
        assert product_service.save_product(db, user_id, prod_id, note="Want this for work")
        assert product_service.is_product_saved(db, user_id, prod_id)

        saved = product_service.get_saved_products(db, user_id)
        assert len(saved) == 1
        assert saved[0]["id"] == prod_id
        assert saved[0]["note"] == "Want this for work"

        # Unsave
        assert product_service.unsave_product(db, user_id, prod_id)
        assert not product_service.is_product_saved(db, user_id, prod_id)

        # Dismissal
        assert product_service.dismiss_product(db, user_id, prod_id, reason="too_expensive")
        dismissed = product_service.get_dismissed_product_ids(db, user_id)
        assert prod_id in dismissed


def test_affiliate_click_tracking(app):
    """Verify outbound referral tracking generates unique click ID and parameters."""
    with app.app_context():
        db = get_db()
        user = auth_service.create_user(db, "clickuser@example.com", "pass12345", is_verified=True)
        prod = product_service.create_product(
            db, partner_id=None, sku="SKU-CLICK", title="Kindle Paperwhite",
            description="E-reader", category="learning", brand="Amazon",
            price=139.99, product_url="https://store.example.com/item?id=99"
        )

        tracking_url = product_service.track_affiliate_click(db, prod["id"], user_id=user["id"])
        assert "click_id=" in tracking_url
        assert "utm_source=feedops_discovery" in tracking_url

        # Check click row in DB
        click_row = db.execute("SELECT * FROM affiliate_clicks WHERE product_id = ?", (prod["id"],)).fetchone()
        assert click_row is not None
        assert click_row["user_id"] == user["id"]


def test_csv_validation_and_import(app):
    """Verify CSV validation rules and deduplication."""
    # 1. Missing required columns
    bad_csv = "sku,title,price\nSKU-1,No Category,99.99"
    items, errors = product_service.parse_and_validate_csv(bad_csv)
    assert len(items) == 0
    assert any("missing mandatory columns" in e.lower() for e in errors)

    # 2. Valid CSV with duplicates
    good_csv = (
        "sku,title,category,price,currency,availability,brand,product_url\n"
        "SKU-A,Product A,electronics,49.99,USD,in_stock,BrandA,https://example.com/a\n"
        "SKU-B,Product B,fashion,29.99,USD,in_stock,BrandB,https://example.com/b\n"
        "SKU-A,Product A Duplicate,electronics,49.99,USD,in_stock,BrandA,https://example.com/a\n"
    )
    items, errors = product_service.parse_and_validate_csv(good_csv)
    assert len(items) == 2
    assert any("duplicate sku 'sku-a'" in e.lower() for e in errors)

    # 3. Batch import into database
    with app.app_context():
        db = get_db()
        res = product_service.import_products_batch(db, partner_id=1, products_list=items)
        assert res["imported"] == 2

        # Verify items in database
        prod_a = db.execute("SELECT * FROM products WHERE sku = 'SKU-A'").fetchone()
        assert prod_a is not None
        assert prod_a["price"] == 49.99

        # Re-importing with updated price updates existing record (deduplication)
        items[0]["price"] = 39.99
        res_update = product_service.import_products_batch(db, partner_id=1, products_list=[items[0]])
        assert res_update["imported"] == 1

        updated_a = db.execute("SELECT * FROM products WHERE sku = 'SKU-A'").fetchone()
        assert updated_a["price"] == 39.99


def test_affiliate_conversion_recording_and_webhook(app, client):
    """Verify recording conversions via service and webhook API."""
    with app.app_context():
        db = get_db()
        prod = product_service.create_product(
            db, partner_id=None, sku="SKU-CONV", title="Smart TV 55-inch",
            category="electronics", price=499.99, product_url="https://store.example.com/tv"
        )
        tracking_url = product_service.track_affiliate_click(db, prod["id"])
        import urllib.parse
        parsed = urllib.parse.urlparse(tracking_url)
        qs = urllib.parse.parse_qs(parsed.query)
        click_id = qs["click_id"][0]

    # 1. Webhook missing click_id -> 400
    res_bad = client.post("/api/v1/affiliate/conversion", json={"amount": 499.99})
    assert res_bad.status_code == 400

    # 2. Webhook invalid click_id -> 404
    res_not_found = client.post("/api/v1/affiliate/conversion", json={"click_id": "nonexistent-click-id"})
    assert res_not_found.status_code == 404

    # 3. Malformed amounts (negative amount or commission > amount) -> 400
    res_neg = client.post("/api/v1/affiliate/conversion", json={"click_id": click_id, "amount": -10.0})
    assert res_neg.status_code == 400
    res_excess_comm = client.post("/api/v1/affiliate/conversion", json={"click_id": click_id, "amount": 50.0, "commission": 100.0})
    assert res_excess_comm.status_code == 400

    # 4. Webhook success -> 200
    res_ok = client.post("/api/v1/affiliate/conversion", json={
        "click_id": click_id,
        "order_id": "ORD-12345",
        "amount": 499.99,
        "commission": 25.00
    })
    assert res_ok.status_code == 200
    data = res_ok.get_json()
    assert data["status"] == "ok"
    assert data["click_id"] == click_id
    assert data["order_id"] == "ORD-12345"
    assert data["idempotent"] is False

    # 5. Idempotent re-submission with same click_id and order_id -> 200 with idempotent: True
    res_replay = client.post("/api/v1/affiliate/conversion", json={
        "click_id": click_id,
        "order_id": "ORD-12345",
        "amount": 499.99,
        "commission": 25.00
    })
    assert res_replay.status_code == 200
    assert res_replay.get_json()["idempotent"] is True

    # 6. Duplicate conversion on same click with different order_id -> 409 Conflict
    res_dup = client.post("/api/v1/affiliate/conversion", json={
        "click_id": click_id,
        "order_id": "ORD-DIFFERENT",
        "amount": 100.00
    })
    assert res_dup.status_code == 409

    # 7. Signature verification tests
    import hmac, hashlib, json, time
    test_secret = "affiliate-test-secret-key"
    app.config["AFFILIATE_WEBHOOK_SECRET"] = test_secret

    # New click for signature testing
    with app.app_context():
        db = get_db()
        sig_url = product_service.track_affiliate_click(db, prod["id"])
        sig_click_id = urllib.parse.parse_qs(urllib.parse.urlparse(sig_url).query)["click_id"][0]

    payload = {"click_id": sig_click_id, "order_id": "ORD-SIG-1", "amount": 299.99, "commission": 15.00}
    raw_payload = json.dumps(payload).encode("utf-8")

    # Missing signature when secret configured -> 401
    res_unauth = client.post("/api/v1/affiliate/conversion", data=raw_payload, content_type="application/json")
    assert res_unauth.status_code == 401

    # Invalid signature -> 401
    res_bad_sig = client.post(
        "/api/v1/affiliate/conversion",
        data=raw_payload,
        content_type="application/json",
        headers={"X-FeedOps-Signature": "invalid-hmac-hex"}
    )
    assert res_bad_sig.status_code == 401

    # Valid signature -> 200
    valid_sig = hmac.new(test_secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
    res_valid_sig = client.post(
        "/api/v1/affiliate/conversion",
        data=raw_payload,
        content_type="application/json",
        headers={"X-FeedOps-Signature": valid_sig}
    )
    assert res_valid_sig.status_code == 200

    # Expired timestamp header -> 400
    res_expired = client.post(
        "/api/v1/affiliate/conversion",
        data=raw_payload,
        content_type="application/json",
        headers={
            "X-FeedOps-Signature": valid_sig,
            "X-Timestamp": str(time.time() - 600)  # 10 minutes ago
        }
    )
    assert res_expired.status_code == 400

    # Clean up config for other tests
    app.config["AFFILIATE_WEBHOOK_SECRET"] = ""



def test_cli_commands(app, monkeypatch):
    """Verify CLI commands refresh-feeds and check-price-alerts execute successfully."""
    from app.services import feed_service
    runner = app.test_cli_runner()

    monkeypatch.setattr(feed_service, "_fetch_bytes", lambda url, **k: b"<rss></rss>")
    result_refresh = runner.invoke(args=["refresh-feeds"])
    assert result_refresh.exit_code == 0
    assert "Refreshed" in result_refresh.output

    result_alerts = runner.invoke(args=["check-price-alerts"])
    assert result_alerts.exit_code == 0
    assert "Price alert monitor" in result_alerts.output


def test_fts5_search_and_synchronization(app):
    """Verify FTS5 search, synchronization triggers, and SQL injection safety."""
    with app.app_context():
        db = get_db()
        p = product_service.create_product(
            db, partner_id=None, sku="SKU-FTS-1",
            title="Logitech MX Master 3S Wireless Ergonomic Mouse",
            description="Quiet clicks with 8K DPI any-surface tracking sensor",
            category="electronics", brand="Logitech", price=99.99,
            product_url="https://example.com/mx3s"
        )
        pid = p["id"]

        # 1. Search by title keyword
        res = product_service.search_products(db, query="Ergonomic Mouse")
        assert any(item["id"] == pid for item in res)

        # 2. Search by description keyword
        res_desc = product_service.search_products(db, query="sensor clicks")
        assert any(item["id"] == pid for item in res_desc)

        # 3. Unusual input (punctuation, quotes, syntax symbols)
        res_unusual = product_service.search_products(db, query='MX-Master (3S) "Quiet" * clicks!')
        assert any(item["id"] == pid for item in res_unusual)

        # 4. SQL injection attempt in query
        res_sqli = product_service.search_products(db, query="' OR '1'='1' --")
        # Should not error and should safely return no or matching items
        assert isinstance(res_sqli, list)

        # 5. Synchronization test: Update product and verify FTS updates
        db.execute(
            "UPDATE products SET title = ?, description = ? WHERE id = ?",
            ("Logitech MX Mechanical Keyboard", "Low profile tactile switches", pid)
        )
        db.commit()

        # Old search should no longer match
        res_old = product_service.search_products(db, query="Ergonomic Mouse")
        assert not any(item["id"] == pid for item in res_old)

        # New search matches updated content
        res_new = product_service.search_products(db, query="Tactile Switches Mechanical")
        assert any(item["id"] == pid for item in res_new)


def test_search_products_empty_and_string_price_filters(app, client):
    """Verify that search_products handles empty, invalid, and formatted price strings without binding errors."""
    with app.app_context():
        db = get_db()
        p = product_service.create_product(
            db, partner_id=None, sku="SKU-PRICE-TEST",
            title="Premium Wireless Soundbar",
            description="Dolby Atmos soundbar with wireless subwoofer",
            category="electronics", brand="Apex", price=12500.0,
            product_url="https://example.com/soundbar"
        )
        pid = p["id"]

        # 1. Empty strings for min_price and max_price (as sent by HTML form filters)
        res_empty = product_service.search_products(db, min_price="", max_price="")
        assert any(item["id"] == pid for item in res_empty)

        # 2. Formatted strings with commas and currency signs
        res_formatted = product_service.search_products(db, min_price="₹10,000", max_price="$20,000")
        assert any(item["id"] == pid for item in res_formatted)

        # 3. Invalid non-numeric strings safely ignored
        res_invalid = product_service.search_products(db, min_price="invalid", max_price="foo")
        assert any(item["id"] == pid for item in res_invalid)

    # 4. End-to-end route check with empty GET query parameters
    route_res = client.get("/products?q=&category=&brand=&min_price=&max_price=&availability=")
    assert route_res.status_code == 200
    assert b"Product Catalogue" in route_res.data



