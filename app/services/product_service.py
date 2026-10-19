"""Product service for catalogue management, multi-filter search, CSV ingestion,
saved products, dismissals, and affiliate click tracking.
"""

import csv
import io
import re
import secrets
import urllib.parse
from datetime import datetime, timezone

VALID_AVAILABILITIES = {"in_stock", "out_of_stock", "preorder"}
DEFAULT_CURRENCY = "USD"
VALID_CATEGORIES = {
    "electronics", "fashion", "home", "groceries", "sports",
    "travel", "learning", "automotive", "general",
}


def create_product(db, partner_id: int = None, sku: str = "", title: str = "", description: str = "",
                   category: str = "general", brand: str = None, price: float = 0.0, currency: str = "USD",
                   availability: str = "in_stock", image_url: str = None, product_url: str = "",
                   feed_source: str = "manual", is_sponsored: bool = False, moderation_status: str = "approved"):
    """Create or update a product item in the catalogue."""
    sku = (sku or "").strip()
    title = (title or "").strip()
    category = (category or "").strip().lower()
    product_url = (product_url or "").strip()

    if not sku:
        raise ValueError("SKU / Product ID is required.")
    if not title:
        raise ValueError("Product title is required.")
    if not category:
        category = "general"
    if not product_url:
        raise ValueError("Product URL is required.")
    try:
        price = float(price)
        if price < 0:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError("Price must be a non-negative number.")

    avail = (availability or "").strip().lower()
    if avail not in VALID_AVAILABILITIES:
        avail = "in_stock"

    now = datetime.now(timezone.utc).isoformat()
    cur = db.execute(
        """INSERT INTO products (
               partner_id, sku, title, description, category, brand, price,
               currency, availability, image_url, product_url, feed_source,
               is_sponsored, moderation_status, last_updated_at, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            partner_id, sku, title[:500], description, category[:100], (brand or "").strip()[:100] or None,
            price, (currency or DEFAULT_CURRENCY).strip().upper()[:10], avail,
            image_url, product_url, feed_source, 1 if is_sponsored else 0,
            moderation_status, now, now
        ),
    )
    db.commit()
    return get_product_by_id(db, cur.lastrowid)


def get_product_by_id(db, product_id: int):
    """Retrieve product by ID with partner information."""
    sql = """
        SELECT p.*, pt.business_name AS partner_name, pt.website AS partner_website
        FROM products p
        LEFT JOIN partners pt ON p.partner_id = pt.id
        WHERE p.id = ?
    """
    row = db.execute(sql, (product_id,)).fetchone()
    return dict(row) if row else None


def list_products(db, limit: int = 50, offset: int = 0, moderation_status: str = "approved"):
    """List products ordered by ID desc."""
    sql = """
        SELECT p.*, pt.business_name AS partner_name
        FROM products p
        LEFT JOIN partners pt ON p.partner_id = pt.id
        WHERE (? IS NULL OR p.moderation_status = ?)
        ORDER BY p.id DESC
        LIMIT ? OFFSET ?
    """
    rows = db.execute(sql, (moderation_status, moderation_status, limit, offset)).fetchall()
    return [dict(r) for r in rows]


def _sanitize_fts_query(query: str) -> str:
    """Sanitize user query into safe FTS5 prefix tokens."""
    import re
    tokens = re.findall(r"[\w]+", query)
    if not tokens:
        return ""
    return " ".join(f'"{t}"*' for t in tokens)


def search_products(db, query: str = None, category: str = None, min_price: float = None,
                    max_price: float = None, brand: str = None, availability: str = None,
                    partner_id: int = None, limit: int = 50, offset: int = 0,
                    moderation_status: str = "approved"):
    """Multi-filter search across product catalog with SQLite FTS5 acceleration."""
    where = []
    params = []

    if moderation_status:
        where.append("p.moderation_status = ?")
        params.append(moderation_status)

    if query and query.strip():
        used_fts = False
        fts_query = _sanitize_fts_query(query.strip())
        if fts_query:
            try:
                # Verify products_fts table is available
                db.execute("SELECT 1 FROM products_fts LIMIT 0")
                where.append("p.id IN (SELECT rowid FROM products_fts WHERE products_fts MATCH ?)")
                params.append(fts_query)
                used_fts = True
            except Exception:
                used_fts = False

        if not used_fts:
            q = f"%{query.strip().replace('%', '\\%').replace('_', '\\_')}%"
            where.append("(p.title LIKE ? ESCAPE '\\' OR p.description LIKE ? ESCAPE '\\' OR p.brand LIKE ? ESCAPE '\\')")
            params.extend([q, q, q])


    if category and category.strip():
        where.append("p.category = ? COLLATE NOCASE")
        params.append(category.strip().lower())

    if brand and brand.strip():
        where.append("p.brand = ? COLLATE NOCASE")
        params.append(brand.strip())

    if availability and availability.strip():
        where.append("p.availability = ?")
        params.append(availability.strip().lower())

    if partner_id is not None:
        where.append("p.partner_id = ?")
        params.append(partner_id)

    if min_price is not None and str(min_price).strip() != "":
        try:
            val = float(str(min_price).replace(",", "").replace("$", "").replace("₹", "").strip())
            where.append("p.price >= ?")
            params.append(val)
        except (ValueError, TypeError):
            pass

    if max_price is not None and str(max_price).strip() != "":
        try:
            val = float(str(max_price).replace(",", "").replace("$", "").replace("₹", "").strip())
            where.append("p.price <= ?")
            params.append(val)
        except (ValueError, TypeError):
            pass


    sql = """
        SELECT p.*, pt.business_name AS partner_name
        FROM products p
        LEFT JOIN partners pt ON p.partner_id = pt.id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += " ORDER BY p.id DESC LIMIT ? OFFSET ?"
    params.extend([min(max(limit, 1), 100), max(offset, 0)])

    rows = db.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def get_product_categories(db):
    """Retrieve distinct categories with product counts."""
    rows = db.execute(
        """SELECT category, COUNT(*) as count
           FROM products
           WHERE moderation_status = 'approved'
           GROUP BY category
           ORDER BY count DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_product_brands(db):
    """Retrieve distinct brands with product counts."""
    rows = db.execute(
        """SELECT brand, COUNT(*) as count
           FROM products
           WHERE brand IS NOT NULL AND brand != '' AND moderation_status = 'approved'
           GROUP BY brand
           ORDER BY count DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Saved Items & Wishlist
# ---------------------------------------------------------------------------

def save_product(db, user_id: int, product_id: int, note: str = None):
    """Save/shortlist a product for a user."""
    try:
        db.execute(
            """INSERT INTO saved_items (user_id, product_id, note)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, product_id) DO UPDATE SET note = excluded.note""",
            (user_id, product_id, note),
        )
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


def unsave_product(db, user_id: int, product_id: int):
    """Remove product from user's saved list."""
    db.execute("DELETE FROM saved_items WHERE user_id = ? AND product_id = ?", (user_id, product_id))
    db.commit()
    return True


def is_product_saved(db, user_id: int, product_id: int) -> bool:
    """Check if a product is saved by user."""
    if not user_id:
        return False
    row = db.execute(
        "SELECT id FROM saved_items WHERE user_id = ? AND product_id = ?",
        (user_id, product_id)
    ).fetchone()
    return bool(row)


def get_saved_products(db, user_id: int):
    """List all products saved by the user."""
    sql = """
        SELECT p.*, s.created_at AS saved_at, s.note, pt.business_name AS partner_name
        FROM saved_items s
        JOIN products p ON s.product_id = p.id
        LEFT JOIN partners pt ON p.partner_id = pt.id
        WHERE s.user_id = ?
        ORDER BY s.id DESC
    """
    rows = db.execute(sql, (user_id,)).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Feedback & Dismissals
# ---------------------------------------------------------------------------

def dismiss_product(db, user_id: int, product_id: int, reason: str = "not_interested"):
    """Record product dismissal with reason."""
    db.execute(
        """INSERT INTO user_feedback (user_id, product_id, action, reason)
           VALUES (?, ?, 'dismiss', ?)""",
        (user_id, product_id, reason),
    )
    db.commit()
    return True


def get_dismissed_product_ids(db, user_id: int):
    """Get list of product IDs dismissed by the user."""
    if not user_id:
        return set()
    rows = db.execute(
        "SELECT DISTINCT product_id FROM user_feedback WHERE user_id = ? AND action = 'dismiss'",
        (user_id,),
    ).fetchall()
    return {r["product_id"] for r in rows}


# ---------------------------------------------------------------------------
# Affiliate Tracking
# ---------------------------------------------------------------------------

def track_affiliate_click(db, product_id: int, user_id: int = None, base_url: str = None):
    """Generate tracked affiliate redirect link and record click."""
    product = get_product_by_id(db, product_id)
    if not product:
        raise ValueError("Product not found.")

    click_id = secrets.token_urlsafe(16)
    target_url = product["product_url"]

    # Append UTM / click_id parameter safely
    parsed = urllib.parse.urlparse(target_url)
    qs = urllib.parse.parse_qs(parsed.query)
    qs["click_id"] = [click_id]
    qs["utm_source"] = ["feedops_discovery"]
    qs["utm_medium"] = ["feed"]
    qs["utm_campaign"] = ["partner_referral"]
    new_query = urllib.parse.urlencode(qs, doseq=True)
    tracking_url = urllib.parse.urlunparse(parsed._replace(query=new_query))

    db.execute(
        """INSERT INTO affiliate_clicks (user_id, product_id, partner_id, click_id, tracking_url)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, product_id, product.get("partner_id"), click_id, tracking_url),
    )

    # Also record click as user engagement for personalization if user logged in
    if user_id:
        db.execute(
            """INSERT INTO user_feedback (user_id, product_id, action, reason)
               VALUES (?, ?, 'click', 'outbound_referral')""",
            (user_id, product_id),
        )
    db.commit()
    return tracking_url


def record_affiliate_conversion(db, click_id: str, order_id: str = None, amount: float = 0.0, commission: float = 0.0):
    """Record affiliate conversion linked to a referral click ID with idempotency and replay protection."""
    import math

    if not click_id or not isinstance(click_id, str) or len(click_id.strip()) == 0 or len(click_id) > 128:
        raise ValueError("Invalid click_id.")
    click_id = click_id.strip()

    try:
        amt = float(amount or 0.0)
        comm = float(commission or 0.0)
    except (ValueError, TypeError):
        raise ValueError("Invalid amount or commission value.")

    if math.isnan(amt) or math.isinf(amt) or amt < 0 or amt > 10000000.0:
        raise ValueError("Conversion amount out of valid range.")
    if math.isnan(comm) or math.isinf(comm) or comm < 0 or comm > amt:
        raise ValueError("Commission out of valid range or exceeds conversion amount.")

    if order_id is not None:
        if not isinstance(order_id, str) or len(order_id.strip()) == 0 or len(order_id) > 128:
            raise ValueError("Invalid order_id format.")
        order_id = order_id.strip()

    row = db.execute("SELECT * FROM affiliate_clicks WHERE click_id = ?", (click_id,)).fetchone()
    if not row:
        raise ValueError(f"Click ID '{click_id}' not found.")

    # Idempotency check: If already converted with identical order_id, return existing record safely
    if row["converted"] == 1:
        if order_id and row["order_id"] == order_id:
            return {
                "status": "ok",
                "idempotent": True,
                "click_id": click_id,
                "product_id": row["product_id"],
                "partner_id": row["partner_id"],
                "order_id": row["order_id"],
                "amount": float(row["conversion_amount"] or 0.0),
                "commission": float(row["commission_amount"] or 0.0),
            }
        raise ValueError(f"Click ID '{click_id}' has already been converted.")

    # Duplicate order protection: Check if order_id has already been converted under a different click
    if order_id:
        existing_order = db.execute(
            "SELECT click_id FROM affiliate_clicks WHERE order_id = ? AND converted = 1",
            (order_id,),
        ).fetchone()
        if existing_order:
            raise ValueError(f"Order ID '{order_id}' has already been recorded.")

    db.execute(
        """UPDATE affiliate_clicks SET
               converted = 1,
               conversion_amount = ?,
               commission_amount = ?,
               order_id = ?,
               converted_at = CURRENT_TIMESTAMP
           WHERE click_id = ?""",
        (amt, comm, order_id, click_id),
    )
    db.commit()
    return {
        "status": "ok",
        "idempotent": False,
        "click_id": click_id,
        "product_id": row["product_id"],
        "partner_id": row["partner_id"],
        "order_id": order_id,
        "amount": amt,
        "commission": comm,
    }




# ---------------------------------------------------------------------------
# Ingestion & Validation (CSV & Feed Data)
# ---------------------------------------------------------------------------

REQUIRED_CSV_FIELDS = ["sku", "title", "category", "price", "product_url"]


def parse_and_validate_csv(csv_text: str, partner_id: int = None, feed_source: str = "csv"):
    """Parse CSV text and validate against required fields.
    Returns (valid_items, error_records).
    """
    valid_items = []
    errors = []

    f = io.StringIO(csv_text.strip())
    reader = csv.DictReader(f)

    if not reader.fieldnames:
        return [], ["CSV file is empty or missing headers."]

    # Normalize header names (lowercase, stripped)
    header_map = {name: name.strip().lower() for name in reader.fieldnames}
    reversed_headers = {v: k for k, v in header_map.items()}

    # Check required fields
    missing_headers = [req for req in REQUIRED_CSV_FIELDS if req not in reversed_headers]
    if missing_headers:
        return [], [f"CSV missing mandatory columns: {', '.join(missing_headers)}"]

    row_num = 1
    seen_skus = set()

    for row in reader:
        row_num += 1
        # Map values using normalized keys
        normalized_row = {header_map[k]: (v or "").strip() for k, v in row.items() if k in header_map}

        sku = normalized_row.get("sku", "")
        title = normalized_row.get("title", "")
        category = normalized_row.get("category", "")
        product_url = normalized_row.get("product_url", "")
        price_raw = normalized_row.get("price", "")

        row_errors = []
        if not sku:
            row_errors.append("Missing SKU/Product ID")
        elif sku in seen_skus:
            row_errors.append(f"Duplicate SKU '{sku}' in upload")
        else:
            seen_skus.add(sku)

        if not title:
            row_errors.append("Missing Title")
        if not category:
            row_errors.append("Missing Category")
        if not product_url or not product_url.startswith(("http://", "https://")):
            row_errors.append("Invalid or missing Product URL (must be http/https)")

        price = 0.0
        try:
            # Strip currency signs if present like $, Rs, etc.
            clean_price = re.sub(r"[^\d.]", "", price_raw)
            price = float(clean_price)
            if price < 0:
                row_errors.append("Price must be non-negative")
        except Exception:
            row_errors.append(f"Invalid price value '{price_raw}'")

        if row_errors:
            errors.append(f"Row {row_num} (SKU: {sku or 'N/A'}): {'; '.join(row_errors)}")
            continue

        valid_items.append({
            "partner_id": partner_id,
            "sku": sku,
            "title": title,
            "description": normalized_row.get("description", ""),
            "category": category.lower(),
            "brand": normalized_row.get("brand") or None,
            "price": price,
            "currency": normalized_row.get("currency", DEFAULT_CURRENCY).upper() or DEFAULT_CURRENCY,
            "availability": normalized_row.get("availability", "in_stock").lower(),
            "image_url": normalized_row.get("image_url") or None,
            "product_url": product_url,
            "feed_source": feed_source,
            "is_sponsored": 1 if normalized_row.get("is_sponsored", "").lower() in ("true", "1", "yes") else 0,
        })

    return valid_items, errors


def import_products_batch(db, partner_id: int, products_list: list):
    """Import a list of validated products into the database.
    Updates existing products with matching (partner_id, sku) or inserts new ones.
    """
    imported = 0
    skipped = 0
    now = datetime.now(timezone.utc).isoformat()

    for item in products_list:
        try:
            # Check if product with partner_id and sku already exists
            existing = db.execute(
                "SELECT id, price FROM products WHERE partner_id = ? AND sku = ?",
                (partner_id, item["sku"]),
            ).fetchone()

            if existing:
                old_price = float(existing["price"] or 0.0)
                new_price = float(item["price"] or 0.0)
                db.execute(
                    """UPDATE products SET
                           title = ?, description = ?, category = ?, brand = ?, price = ?,
                           currency = ?, availability = ?, image_url = ?, product_url = ?,
                           is_sponsored = ?, last_updated_at = ?
                       WHERE id = ?""",
                    (
                        item["title"][:500], item["description"], item["category"][:100],
                        item["brand"], item["price"], item["currency"], item["availability"],
                        item["image_url"], item["product_url"], item["is_sponsored"], now,
                        existing["id"]
                    ),
                )
                if old_price > new_price > 0:
                    try:
                        from app.services import privacy_service
                        privacy_service.trigger_price_drop_alert(db, existing["id"], old_price, new_price)
                    except Exception:
                        pass
            else:
                db.execute(
                    """INSERT INTO products (
                           partner_id, sku, title, description, category, brand, price,
                           currency, availability, image_url, product_url, feed_source,
                           is_sponsored, moderation_status, last_updated_at, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'approved', ?, ?)""",
                    (
                        partner_id, item["sku"], item["title"][:500], item["description"],
                        item["category"][:100], item["brand"], item["price"], item["currency"],
                        item["availability"], item["image_url"], item["product_url"],
                        item["feed_source"], item["is_sponsored"], now, now
                    ),
                )
            imported += 1
        except Exception:
            skipped += 1
            continue

    db.commit()
    return {"imported": imported, "skipped": skipped, "total": len(products_list)}
