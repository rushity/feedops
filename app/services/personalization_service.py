"""Personalization and Recommendation Ranking Service.

Implements personalized ranking for consumer discovery feeds using:
- User-selected interests
- Budget range matching
- Preferred brands
- Saved products history
- Click / interaction signals
- Explicit dismissal suppression / penalties
- Human-understandable recommendation explanations
"""

from datetime import datetime, timezone
import math


def score_product(product: dict, user_preferences: dict, saved_product_ids: set,
                  dismissed_product_ids: set, clicked_categories: dict = None) -> tuple[float, list[str]]:
    """Compute ranking score and human-understandable explanation reasons for a product.
    Returns (score, reasons).
    """
    if product["id"] in dismissed_product_ids:
        return -100.0, ["Dismissed by you"]

    score = 10.0
    reasons = []

    interests = [i.lower() for i in (user_preferences.get("interests") or [])]
    budget_min = float(user_preferences.get("budget_min") or 0)
    budget_max = float(user_preferences.get("budget_max") or 100000)
    preferred_brands = [b.lower() for b in (user_preferences.get("preferred_brands") or [])]
    clicked_categories = clicked_categories or {}

    category = (product.get("category") or "").lower()
    brand = (product.get("brand") or "").lower()
    price = float(product.get("price") or 0)
    availability = (product.get("availability") or "in_stock").lower()
    is_sponsored = bool(product.get("is_sponsored"))

    # 1. Interest match (+35 points)
    if category in interests:
        score += 35.0
        reasons.append(f"Matches your {category.title()} interest")
    elif any(term in category for term in interests):
        score += 20.0
        reasons.append(f"Related to your interests")

    # 2. Budget match (+25 points)
    if budget_min <= price <= budget_max:
        score += 25.0
        reasons.append(f"Within your budget (${budget_min:,.0f} - ${budget_max:,.0f})")
    elif price < budget_min:
        score += 5.0
    else:
        # Penalize items far over budget
        overage_ratio = (price - budget_max) / max(budget_max, 1)
        score -= min(overage_ratio * 15.0, 30.0)

    # 3. Brand affinity (+20 points)
    if brand and any(b in brand for b in preferred_brands):
        score += 20.0
        reasons.append(f"Matches your preferred brand: {product.get('brand')}")

    # 4. Saved items (+30 points)
    if product["id"] in saved_product_ids:
        score += 30.0
        reasons.append("Saved in your shortlist")

    # 5. Engagement affinity (+15 points max)
    if category in clicked_categories:
        click_boost = min(clicked_categories[category] * 5.0, 15.0)
        score += click_boost
        if click_boost >= 10.0 and f"Matches your {category.title()} interest" not in reasons:
            reasons.append(f"Based on your recent browsing in {category.title()}")

    # 6. Availability factor
    if availability == "in_stock":
        score += 10.0
    elif availability == "preorder":
        score += 2.0
        reasons.append("Available for pre-order")
    else:
        score -= 20.0
        reasons.append("Currently out of stock")

    # 7. Freshness boost
    last_updated = product.get("last_updated_at")
    if last_updated:
        try:
            dt = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - dt).days
            if age_days <= 3:
                score += 5.0
                reasons.append("Newly added or updated")
        except Exception:
            pass

    # Default fallback reason if no specific match
    if not reasons:
        reasons.append(f"Popular in {category.title() if category else 'Catalogue'}")

    return round(score, 2), reasons


def get_personalized_feed(db, user_id: int = None, limit: int = 50, offset: int = 0):
    """Generate a ranked, personalized discovery feed with human-understandable explanations.
    Degrades safely to a catalog feed when user is anonymous or has no preferences.
    Sponsored products are retrieved and placed separately to preserve organic ranking integrity.
    """
    from app.services.auth_service import get_user_preferences
    from app.services.product_service import get_saved_products, get_dismissed_product_ids

    # Fetch candidate products
    sql = """
        SELECT p.*, pt.business_name AS partner_name
        FROM products p
        LEFT JOIN partners pt ON p.partner_id = pt.id
        WHERE p.moderation_status = 'approved'
        ORDER BY p.id DESC
        LIMIT 200
    """
    candidates = [dict(r) for r in db.execute(sql).fetchall()]

    if not candidates:
        return []

    # Gather user signals
    user_prefs = {"interests": [], "budget_min": 0, "budget_max": 5000, "preferred_brands": []}
    saved_ids = set()
    dismissed_ids = set()
    clicked_categories = {}

    if user_id:
        user_prefs = get_user_preferences(db, user_id)
        saved_items = get_saved_products(db, user_id)
        saved_ids = {s["id"] for s in saved_items}
        dismissed_ids = get_dismissed_product_ids(db, user_id)

        # Get category engagement history
        clicks = db.execute(
            """SELECT p.category, COUNT(*) as count
               FROM user_feedback uf
               JOIN products p ON uf.product_id = p.id
               WHERE uf.user_id = ? AND uf.action = 'click'
               GROUP BY p.category""",
            (user_id,),
        ).fetchall()
        clicked_categories = {r["category"].lower(): r["count"] for r in clicks if r["category"]}

    # Retrieve dedicated sponsored placements on page 1
    sponsored_items = []
    if offset == 0:
        try:
            from app.services import partner_service
            sponsored = partner_service.get_active_sponsored_products(db, limit=2, user_id=user_id)
            for s in sponsored:
                s["score"] = 1000.0
                s["reasons"] = [f"Sponsored by {s.get('partner_name', 'Partner')}"]
                s["primary_reason"] = f"Promoted: {s.get('campaign_title', 'Featured')}"
                s["is_saved"] = s["id"] in saved_ids
                sponsored_items.append(s)
        except Exception:
            sponsored_items = []

    sponsored_ids = {s["id"] for s in sponsored_items}

    scored_items = []
    for product in candidates:
        if product["id"] in sponsored_ids:
            continue
        score, reasons = score_product(
            product,
            user_preferences=user_prefs,
            saved_product_ids=saved_ids,
            dismissed_product_ids=dismissed_ids,
            clicked_categories=clicked_categories,
        )
        if score > -50:  # Omit completely dismissed products
            item = dict(product)
            item["score"] = score
            item["reasons"] = reasons
            item["primary_reason"] = reasons[0] if reasons else "Recommended for you"
            item["is_saved"] = product["id"] in saved_ids
            scored_items.append(item)

    # Sort organic items descending by relevance score
    scored_items.sort(key=lambda x: x["score"], reverse=True)

    # Combine sponsored placements (first) with organic feed
    all_feed = (sponsored_items if offset == 0 else []) + scored_items
    return all_feed[offset:offset + limit]

