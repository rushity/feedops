"""Rushik-owned tests: search, AI analysis, article routes (additive file).

Covers listing/detail/search behaviour, output validation and AI failure
cases. Does not modify existing tests.
"""
import pytest

from app.database.db import get_db
from app.services import ai_service
from app.services.search_service import get_filter_options, search_articles


@pytest.fixture()
def seeded_app(app):
    with app.app_context():
        db = get_db()
        cur = db.execute(
            "INSERT INTO feeds (url, title) VALUES (?, ?)",
            ("https://tech.example/rss", "TechDaily"),
        )
        tech_id = cur.lastrowid
        cur2 = db.execute(
            "INSERT INTO feeds (url, title) VALUES (?, ?)",
            ("https://biz.example/rss", "BizWire"),
        )
        biz_id = cur2.lastrowid
        db.execute(
            "INSERT INTO articles (feed_id, title, url, summary, category, published_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (tech_id, "AI breakthrough in chip design",
             "https://example.com/ai-chips",
             "A great breakthrough promises faster chips.",
             "technology", "2026-09-01"),
        )
        db.execute(
            "INSERT INTO articles (feed_id, title, url, summary, category, published_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (biz_id, "Market falls amid crisis fears",
             "https://example.com/market",
             "Stocks fall as investors fear losses.",
             "business", "2026-09-05"),
        )
        db.commit()
    return app


def test_search_by_title(seeded_app):
    with seeded_app.app_context():
        res = search_articles(get_db(), "breakthrough")
    assert len(res) == 1
    assert res[0]["title"].startswith("AI breakthrough")


def test_search_by_summary(seeded_app):
    with seeded_app.app_context():
        res = search_articles(get_db(), "investors")
    assert len(res) == 1
    assert "Market falls" in res[0]["title"]


def test_empty_query_returns_empty_list(seeded_app):
    """Stable contract: bare empty search -> []."""
    with seeded_app.app_context():
        assert search_articles(get_db(), "   ") == []


def test_category_filter_without_query(seeded_app):
    with seeded_app.app_context():
        res = search_articles(get_db(), "", category="business")
    assert len(res) == 1


def test_source_filter_matches_feed_title(seeded_app):
    with seeded_app.app_context():
        res = search_articles(get_db(), "", source="TechDaily")
    assert len(res) == 1
    assert res[0]["feed_title"] == "TechDaily"


def test_date_filters(seeded_app):
    with seeded_app.app_context():
        db = get_db()
        assert len(search_articles(db, "", date_from="2026-09-01", date_to="2026-09-30")) == 2
        assert len(search_articles(db, "", date_from="2026-09-03")) == 1
        # Invalid dates are ignored, not fatal.
        assert len(search_articles(db, "", date_from="not-a-date")) == 3


def test_like_wildcards_escaped_and_injection_safe(seeded_app):
    with seeded_app.app_context():
        db = get_db()
        assert search_articles(db, "'; DROP TABLE articles; --") == []
        assert search_articles(db, "%") == []  # literal %, not a wildcard
        tables = {r["name"] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"feeds", "articles"} <= tables


def test_limit_clamped(seeded_app):
    with seeded_app.app_context():
        res = search_articles(get_db(), "a", limit=1000)
    assert len(res) <= 100


def test_filter_options(seeded_app):
    with seeded_app.app_context():
        opts = get_filter_options(get_db())
    assert "TechDaily" in opts["sources"]
    assert "technology" in opts["categories"]


def test_summarize_contract():
    assert ai_service.summarize("", 10) == ""
    assert ai_service.summarize("short", 300) == "short"
    long = "First sentence. Second sentence. " + "word " * 200
    out = ai_service.summarize(long, 50)
    assert len(out) <= 60


def test_categorize_contract():
    assert ai_service.categorize("new AI chip launch") == "technology"
    assert ai_service.categorize("completely unrelated xyz") == "uncategorized"


def test_analyze_article_fallback_shape():
    out = ai_service.analyze_article({
        "title": "AI breakthrough brings great success",
        "summary": "Excellent growth reported.",
    })
    assert out["summary"]
    assert isinstance(out["topics"], list) and out["topics"]
    assert out["sentiment"] in ("positive", "neutral", "negative")
    assert 0.0 <= out["relevance_score"] <= 1.0
    assert out["fallback_used"] is True
    assert out["validated"] is True


def test_analyze_article_empty_never_raises():
    out = ai_service.analyze_article({"title": "", "summary": ""})
    assert out["sentiment"] == "neutral"


def test_analyze_article_accepts_row_objects(seeded_app):
    with seeded_app.app_context():
        rows = search_articles(get_db(), "breakthrough")
        out = ai_service.analyze_article(rows[0])
    assert out["summary"]


def test_validate_analysis_clamps_bad_output():
    cleaned, errors = ai_service.validate_analysis({
        "summary": "   ", "topics": "not-a-list", "sentiment": "ecstatic",
        "sentiment_score": "NaN-ish", "relevance_score": 99,
    })
    assert errors
    assert cleaned["sentiment"] == "neutral"
    assert cleaned["topics"] == ["uncategorized"]
    assert cleaned["relevance_score"] == 1.0


def test_remote_timeout_degrades(monkeypatch):
    monkeypatch.setenv("FEEDOPS_AI_ENABLED", "true")
    monkeypatch.setenv("FEEDOPS_AI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.ai_service._call_remote_ai",
        lambda *a, **k: (_ for _ in ()).throw(TimeoutError("timed out")),
    )
    out = ai_service.analyze_article({"title": "Hello", "summary": "world"})
    assert out["fallback_used"] is True
    assert any("timed out" in e for e in out["errors"])


def test_remote_rate_limit_degrades(monkeypatch):
    monkeypatch.setenv("FEEDOPS_AI_ENABLED", "true")
    monkeypatch.setenv("FEEDOPS_AI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.ai_service._call_remote_ai",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("AI rate limit exceeded (HTTP 429)")),
    )
    out = ai_service.analyze_article({"title": "Market news", "summary": "Stocks fall."})
    assert out["fallback_used"] is True


def test_missing_key_uses_fallback(monkeypatch):
    monkeypatch.setenv("FEEDOPS_AI_ENABLED", "true")
    monkeypatch.delenv("FEEDOPS_AI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = ai_service.analyze_article({"title": "Sports win", "summary": "The team won."})
    assert out["provider"] == "fallback"


def test_no_hardcoded_credentials():
    import inspect
    src = inspect.getsource(ai_service)
    assert "sk-" not in src
    assert "ghp_" not in src
    assert "github_pat_" not in src


def test_article_list_with_filters(client, seeded_app):
    assert client.get("/articles/").status_code == 200
    res = client.get("/articles/?category=business")
    assert res.status_code == 200
    assert b"Market falls" in res.data
    assert b"AI breakthrough" not in res.data


def test_article_detail_analyze_and_404(client, seeded_app):
    assert client.get("/articles/9999").status_code == 404
    res = client.get("/articles/1?analyze=1")
    assert res.status_code == 200
    assert b"AI analysis" in res.data


def test_search_page_filters(client, seeded_app):
    res = client.get("/search/?q=breakthrough")
    assert res.status_code == 200
    assert b"AI breakthrough" in res.data
    empty = client.get("/search/?q=no-such-thing-xyz")
    assert b"No articles found" in empty.data
