"""Frontend and dashboard integration tests. Owner: Dhruv."""
import pytest
from app.database.db import get_db
from app.services import feed_service

SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Frontend Test Feed</title><link>https://example.com/frontend</link><description>Frontend Test</description>
<item><title>Frontend News</title><link>https://example.com/news1</link>
<description>UI test article</description><category>technology</category></item>
</channel></rss>"""


def test_base_layout_structure(client):
    """Verify base template renders navigation, brand, search form, and assets."""
    res = client.get("/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "FeedOps" in html
    assert "Dashboard" in html
    assert "Feeds" in html
    assert "Articles" in html
    assert 'role="search"' in html
    assert 'href="/static/css/style.css"' in html
    assert 'src="/static/js/main.js"' in html
    assert 'href="/health"' in html


def test_dashboard_empty_state(app, client):
    """Verify dashboard displays clean empty state when no feeds/articles exist."""
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM articles")
        db.execute("DELETE FROM feeds")
        db.commit()

    res = client.get("/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Feed Management Hub" in html
    assert "No articles" in html
    assert "0" in html


def test_dashboard_health_metrics_with_data(app, client):
    """Verify dashboard displays healthy/error feed metrics and latest sync time."""
    with app.app_context():
        db = get_db()
        # Seed healthy feed
        cur1 = db.execute(
            "INSERT INTO feeds (url, title, last_fetched_at, last_fetch_status) "
            "VALUES (?, ?, ?, ?)",
            ("https://healthy.example/rss", "Healthy Feed", "2026-10-16T12:00:00Z", "ok"),
        )
        # Seed errored feed
        db.execute(
            "INSERT INTO feeds (url, title, last_fetched_at, last_fetch_status, last_error) "
            "VALUES (?, ?, ?, ?, ?)",
            ("https://error.example/rss", "Error Feed", "2026-10-16T11:00:00Z", "error", "Network timeout"),
        )
        # Seed pending feed
        db.execute(
            "INSERT INTO feeds (url, title) VALUES (?, ?)",
            ("https://pending.example/rss", "Pending Feed"),
        )
        db.execute(
            "INSERT INTO articles (feed_id, title, url, summary, category, published_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cur1.lastrowid, "Healthy Article", "https://healthy.example/a1", "Summary 1", "technology", "2026-10-16T12:00:00Z"),
        )
        db.commit()

    res = client.get("/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Healthy Feeds" in html
    assert "Ingestion Errors" in html
    assert "Healthy Article" in html
    assert "Healthy Feed" in html
    assert "2026-10-16" in html


def test_dashboard_null_status_and_timestamps(app, client):
    """Handle null status and timestamp values in database without crashing."""
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM articles")
        db.execute("DELETE FROM feeds")
        db.execute(
            "INSERT INTO feeds (url, title, last_fetched_at, last_fetch_status, last_error) "
            "VALUES (?, ?, NULL, NULL, NULL)",
            ("https://null.example/rss", "Null Status Feed"),
        )
        db.commit()

    res = client.get("/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Null Status Feed" in html
    assert "Pending sync" in html


def test_feeds_empty_state(app, client):
    """Verify feeds management view renders empty state when no feeds registered."""
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM articles")
        db.execute("DELETE FROM feeds")
        db.commit()

    res = client.get("/feeds/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "No feeds registered yet" in html


def test_feeds_add_validation_and_errors(client):
    """Verify add feed form attributes and validation error handling."""
    res = client.get("/feeds/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert 'name="url"' in html
    assert 'type="url"' in html
    assert 'required' in html

    # Submit bad URL
    bad_res = client.post("/feeds/", data={"url": "not-a-url", "title": "Bad"})
    assert bad_res.status_code == 200
    bad_html = bad_res.data.decode("utf-8")
    assert "alert alert-error" in bad_html or "error" in bad_html
    assert "http" in bad_html.lower()


def test_feeds_add_success_and_duplicate(app, client):
    """Verify adding feed and rejecting duplicate URL."""
    res = client.post(
        "/feeds/",
        data={"url": "https://unique.example/rss", "title": "Unique Feed"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Unique Feed" in html

    # Duplicate attempt
    dupe_res = client.post(
        "/feeds/",
        data={"url": "https://unique.example/rss", "title": "Duplicate Feed"},
    )
    assert dupe_res.status_code == 200
    dupe_html = dupe_res.data.decode("utf-8")
    assert "already registered" in dupe_html.lower()


def test_feeds_status_badges_and_timestamps(app, client):
    """Verify status badges (Active, Failed, Pending), timestamps, and error messages."""
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO feeds (url, title, last_fetched_at, last_fetch_status) "
            "VALUES (?, ?, ?, ?)",
            ("https://ok.example/rss", "OK Feed", "2026-10-16T14:30:00Z", "ok"),
        )
        db.execute(
            "INSERT INTO feeds (url, title, last_fetched_at, last_fetch_status, last_error) "
            "VALUES (?, ?, ?, ?, ?)",
            ("https://fail.example/rss", "Failed Feed", "2026-10-16T14:35:00Z", "error", "Remote server unreachable"),
        )
        db.execute(
            "INSERT INTO feeds (url, title) VALUES (?, ?)",
            ("https://unfetched.example/rss", "Unfetched Feed"),
        )
        db.commit()

    res = client.get("/feeds/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Active" in html
    assert "Failed" in html
    assert "Pending" in html
    assert "Remote server unreachable" in html
    assert "2026-10-16T14:30:00" in html


def test_feeds_refresh_success_banner(app, client, monkeypatch):
    """Verify refreshing feed displays success banner and updated counts."""
    with app.app_context():
        db = get_db()
        cur = db.execute("INSERT INTO feeds (url, title) VALUES (?, ?)", ("https://refreshable.example/rss", "Refreshable"))
        db.commit()
        fid = cur.lastrowid

    monkeypatch.setattr(feed_service, "_fetch_bytes", lambda url, **k: SAMPLE_RSS)
    res = client.post(f"/feeds/{fid}/refresh")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Refreshed" in html
    assert "alert alert-success" in html


def test_feeds_refresh_failure_behavior(app, client, monkeypatch):
    """Verify refresh route handles errors gracefully and renders error banner."""
    with app.app_context():
        db = get_db()
        cur = db.execute("INSERT INTO feeds (url, title) VALUES (?, ?)", ("https://error-refresh.example/rss", "Error Refresh"))
        db.commit()
        fid = cur.lastrowid

    def boom(url, **k):
        raise RuntimeError("Fetch connection timed out")

    monkeypatch.setattr(feed_service, "_fetch_bytes", boom)
    res = client.post(f"/feeds/{fid}/refresh")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "alert alert-error" in html
    assert "Fetch connection timed out" in html


def test_integration_articles_search_and_ai_routes(client):
    """Ensure articles, search, and AI analysis routes continue rendering properly."""
    res_art = client.get("/articles/")
    assert res_art.status_code == 200
    assert "Hello FeedOps" in res_art.data.decode("utf-8")

    res_search = client.get("/search/?q=Hello")
    assert res_search.status_code == 200
    assert "Hello FeedOps" in res_search.data.decode("utf-8")

    res_detail = client.get("/articles/1")
    assert res_detail.status_code == 200
    assert "Hello FeedOps" in res_detail.data.decode("utf-8")

    res_ai = client.get("/articles/1?analyze=1")
    assert res_ai.status_code == 200
    assert "AI analysis" in res_ai.data.decode("utf-8")
