"""Tests for Personalization Ranking Engine and Recommendation Explanations."""

import pytest
from app.database.db import get_db
from app.services import personalization_service, product_service, auth_service


def test_ranking_scoring_and_explanations(app):
    """Verify ranking score calculations and human-understandable explanation generation."""
    with app.app_context():
        db = get_db()
        user = auth_service.create_user(db, "rankuser@example.com", "pass12345", is_verified=True)
        user_id = user["id"]

        auth_service.update_user_preferences(
            db,
            user_id=user_id,
            interests=["electronics"],
            budget_min=100.0,
            budget_max=600.0,
            preferred_brands=["Sony"],
        )

        p_match = product_service.create_product(
            db, partner_id=None, sku="SKU-MATCH", title="Sony Wireless Earbuds",
            description="Sony ANC Earbuds", category="electronics", brand="Sony",
            price=249.99, availability="in_stock", product_url="https://example.com/earbuds"
        )

        p_overbudget = product_service.create_product(
            db, partner_id=None, sku="SKU-EXPENSIVE", title="Generic High-End Machine",
            description="High cost tool", category="automotive", brand="OtherBrand",
            price=5000.0, availability="in_stock", product_url="https://example.com/auto"
        )

        feed = personalization_service.get_personalized_feed(db, user_id=user_id)
        assert len(feed) >= 2

        # Top product should be the matching Sony electronics product
        top = feed[0]
        assert top["id"] == p_match["id"]
        assert top["score"] > feed[1]["score"]

        # Check explanation reasons
        assert any("matches your electronics interest" in r.lower() for r in top["reasons"])
        assert any("within your budget" in r.lower() for r in top["reasons"])
        assert any("matches your preferred brand: sony" in r.lower() for r in top["reasons"])


def test_dismissed_product_suppression(app):
    """Verify dismissed products are suppressed from the feed."""
    with app.app_context():
        db = get_db()
        user = auth_service.create_user(db, "dismissuser@example.com", "pass12345", is_verified=True)
        user_id = user["id"]

        p1 = product_service.create_product(
            db, partner_id=None, sku="SKU-DISMISS", title="Unwanted Gadget",
            description="Will be dismissed", category="general", price=29.99,
            product_url="https://example.com/gadget"
        )

        # Before dismissal
        feed_before = personalization_service.get_personalized_feed(db, user_id=user_id)
        assert any(item["id"] == p1["id"] for item in feed_before)

        # Dismiss product
        product_service.dismiss_product(db, user_id, p1["id"], reason="not_interested")

        # After dismissal: product should be excluded from personalized feed
        feed_after = personalization_service.get_personalized_feed(db, user_id=user_id)
        assert not any(item["id"] == p1["id"] for item in feed_after)


def test_anonymous_fallback_feed(app):
    """Verify unauthenticated/anonymous users receive a valid fallback catalogue feed."""
    with app.app_context():
        db = get_db()
        feed = personalization_service.get_personalized_feed(db, user_id=None)
        assert isinstance(feed, list)
        if feed:
            assert "primary_reason" in feed[0]
            assert "score" in feed[0]
