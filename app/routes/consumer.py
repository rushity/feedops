"""Consumer Discovery and Product Routes."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, abort
from app.database.db import get_db
from app.services import product_service, personalization_service, auth_service

consumer_bp = Blueprint("consumer", __name__)


@consumer_bp.route("/discover")
def discover():
    """Personalized AI Discovery Feed."""
    db = get_db()
    user_id = session.get("user_id")
    page = max(int(request.args.get("page", 1)), 1)
    limit = 20
    offset = (page - 1) * limit

    feed_items = personalization_service.get_personalized_feed(db, user_id=user_id, limit=limit, offset=offset)
    categories = product_service.get_product_categories(db)

    user_prefs = None
    if user_id:
        user_prefs = auth_service.get_user_preferences(db, user_id)

    return render_template(
        "discover.html",
        feed_items=feed_items,
        categories=categories,
        user_prefs=user_prefs,
        page=page,
    )


@consumer_bp.route("/products")
def products():
    """Browse and multi-filter product catalogue."""
    db = get_db()
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    brand = request.args.get("brand", "").strip()
    min_price = request.args.get("min_price", "").strip() or None
    max_price = request.args.get("max_price", "").strip() or None
    availability = request.args.get("availability", "").strip()


    items = product_service.search_products(
        db,
        query=query or None,
        category=category or None,
        min_price=min_price,
        max_price=max_price,
        brand=brand or None,
        availability=availability or None,
        limit=50,
    )

    categories = product_service.get_product_categories(db)
    brands = product_service.get_product_brands(db)

    user_id = session.get("user_id")
    saved_ids = set()
    if user_id:
        saved = product_service.get_saved_products(db, user_id)
        saved_ids = {s["id"] for s in saved}

    return render_template(
        "products.html",
        products=items,
        categories=categories,
        brands=brands,
        saved_ids=saved_ids,
        query=query,
        category=category,
        brand=brand,
        min_price=min_price,
        max_price=max_price,
        availability=availability,
    )


@consumer_bp.route("/products/<int:product_id>")
def product_detail(product_id: int):
    """Detailed view for a product item."""
    db = get_db()
    product = product_service.get_product_by_id(db, product_id)
    if not product:
        abort(404)

    user_id = session.get("user_id")
    is_saved = product_service.is_product_saved(db, user_id, product_id) if user_id else False

    # Compute personal score and reasons for this product
    user_prefs = auth_service.get_user_preferences(db, user_id) if user_id else {}
    score, reasons = personalization_service.score_product(
        product,
        user_preferences=user_prefs,
        saved_product_ids={product_id} if is_saved else set(),
        dismissed_product_ids=set(),
    )

    return render_template(
        "product_detail.html",
        product=product,
        is_saved=is_saved,
        reasons=reasons,
        score=score,
    )


@consumer_bp.route("/products/<int:product_id>/save", methods=["POST"])
@auth_service.login_required
def save_product(product_id: int):
    """Save/shortlist a product."""
    db = get_db()
    user_id = session["user_id"]
    note = request.form.get("note")
    product_service.save_product(db, user_id, product_id, note=note)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(status="ok", is_saved=True)
    flash("Product added to your saved shortlist.", "success")
    return redirect(request.referrer or url_for("consumer.discover"))


@consumer_bp.route("/products/<int:product_id>/unsave", methods=["POST"])
@auth_service.login_required
def unsave_product(product_id: int):
    """Remove product from saved shortlist."""
    db = get_db()
    user_id = session["user_id"]
    product_service.unsave_product(db, user_id, product_id)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(status="ok", is_saved=False)
    flash("Product removed from saved shortlist.", "info")
    return redirect(request.referrer or url_for("consumer.saved_items"))


@consumer_bp.route("/products/<int:product_id>/dismiss", methods=["POST"])
@auth_service.login_required
def dismiss_product(product_id: int):
    """Dismiss a product and exclude it from the discovery feed."""
    db = get_db()
    user_id = session["user_id"]
    reason = request.form.get("reason", "not_interested")
    product_service.dismiss_product(db, user_id, product_id, reason=reason)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(status="ok", dismissed=True)
    flash("Product dismissed. We'll show you fewer items like this.", "info")
    return redirect(request.referrer or url_for("consumer.discover"))


@consumer_bp.route("/saved")
@auth_service.login_required
def saved_items():
    """List of consumer shortlisted / saved products."""
    db = get_db()
    user_id = session["user_id"]
    saved = product_service.get_saved_products(db, user_id)
    return render_template("saved_items.html", saved=saved)


@consumer_bp.route("/products/<int:product_id>/click")
def affiliate_redirect(product_id: int):
    """Outbound referral click tracking."""
    db = get_db()
    user_id = session.get("user_id")
    try:
        tracking_url = product_service.track_affiliate_click(db, product_id, user_id=user_id)
        return redirect(tracking_url)
    except Exception:
        abort(404)


def verify_webhook_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature for webhook requests."""
    if not secret or not signature_header:
        return False
    import hmac
    import hashlib
    sig = signature_header.strip()
    if sig.startswith("sha256="):
        sig = sig[7:]
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig.lower(), expected.lower())


@consumer_bp.route("/api/v1/affiliate/conversion", methods=["POST"])
def affiliate_conversion_webhook():
    """Secure webhook for affiliate networks/merchants to report conversion receipts."""
    from flask import current_app
    import time

    # 1. Signature Verification
    webhook_secret = current_app.config.get("AFFILIATE_WEBHOOK_SECRET")
    sig_header = request.headers.get("X-FeedOps-Signature") or request.headers.get("X-Signature")
    if webhook_secret or sig_header:
        raw_body = request.get_data()
        if not sig_header or not webhook_secret or not verify_webhook_signature(raw_body, sig_header, webhook_secret):
            return jsonify(error="Unauthorized: invalid or missing webhook signature"), 401

    # 2. Replay Protection via Timestamp Header (if provided)
    ts_header = request.headers.get("X-Timestamp")
    if ts_header:
        try:
            req_time = float(ts_header)
            if abs(time.time() - req_time) > 300:  # 5-minute maximum tolerance
                return jsonify(error="Request timestamp expired or skewed"), 400
        except (ValueError, TypeError):
            return jsonify(error="Malformed X-Timestamp header"), 400

    # 3. Payload Extraction & Validation
    data = request.get_json(silent=True)
    if data is None and request.form:
        data = request.form.to_dict()
    if not isinstance(data, dict):
        return jsonify(error="Invalid payload: JSON object required"), 400

    click_id = data.get("click_id")
    if not click_id or not isinstance(click_id, str) or not click_id.strip():
        return jsonify(error="click_id is required"), 400

    order_id = data.get("order_id")
    amount = data.get("amount", 0.0)
    commission = data.get("commission", 0.0)

    db = get_db()
    try:
        result = product_service.record_affiliate_conversion(
            db, click_id=click_id, order_id=order_id, amount=amount, commission=commission
        )
        return jsonify(result), 200
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            return jsonify(error="Referral click ID not found"), 404
        if "already been converted" in msg.lower() or "already been recorded" in msg.lower():
            return jsonify(error="Duplicate conversion record rejected"), 409
        return jsonify(error="Invalid conversion payload"), 400
    except Exception:
        return jsonify(error="Internal server error processing conversion"), 500


