"""Ingestion tests (Rushit). All network is mocked - no external websites."""
import urllib.request

import pytest

from app.database.db import get_db
from app.services import feed_service
from app.services.feed_service import canonicalize_url, fetch_and_store

RSS_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Test Feed</title><link>https://example.com</link><description>test</description>
<item><title>First article</title><link>https://example.com/a1</link>
<description>Summary one</description><pubDate>Mon, 12 Oct 2026 10:00:00 GMT</pubDate>
<category>tech</category></item>
<item><title>Second article</title><link>https://example.com/a2</link>
<description>Summary two</description></item>
</channel></rss>"""

ATOM_SAMPLE = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Atom Feed</title>
<entry><title>Atom One</title><link href="https://example.com/atom1"/>
<summary>Atom summary</summary><updated>2026-10-13T12:00:00Z</updated></entry>
<entry><title>Atom Two</title><link href="https://example.com/atom2"/>
<content>Content body here</content></entry>
</feed>"""

MISSING_FIELDS_RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Odd Feed</title>
<item><link>https://example.com/has-link-no-title</link><description>x</description></item>
<item><title>No link item</title><description>y</description></item>
<item><title>Bad date</title><link>https://example.com/bad-date</link>
<pubDate>not a real date</pubDate></item>
</channel></rss>"""


def _make_feed(app, url="https://example.com/rss-test", title="T"):
    with app.app_context():
        db = get_db()
        return feed_service.create_feed(db, url, title)["id"]


def test_fetch_valid_rss(app, monkeypatch):
    fid = _make_feed(app)
    monkeypatch.setattr(feed_service, "_fetch_bytes", lambda url, **k: RSS_SAMPLE)
    with app.app_context():
        db = get_db()
        result = fetch_and_store(db, fid)
    assert result["status"] == "ok"
    assert result["added"] == 2
    assert result["total"] == 2
    with app.app_context():
        db = get_db()
        rows = db.execute("SELECT title, url, summary FROM articles WHERE feed_id = ?", (fid,)).fetchall()
        assert len(rows) == 2
        feed = feed_service.get_feed(db, fid)
        assert feed["title"] == "Test Feed"  # metadata stored
        assert feed["last_fetch_status"] == "ok"
        assert feed["last_fetched_at"] is not None


def test_fetch_valid_atom(app, monkeypatch):
    fid = _make_feed(app, url="https://example.com/atom-test")
    monkeypatch.setattr(feed_service, "_fetch_bytes", lambda url, **k: ATOM_SAMPLE)
    with app.app_context():
        result = fetch_and_store(get_db(), fid)
    assert result["status"] == "ok"
    assert result["added"] == 2
    with app.app_context():
        feed = feed_service.get_feed(get_db(), fid)
        assert feed["title"] == "Atom Feed"


def test_duplicate_articles_deduped(app, monkeypatch):
    fid = _make_feed(app)
    monkeypatch.setattr(feed_service, "_fetch_bytes", lambda url, **k: RSS_SAMPLE)
    with app.app_context():
        db = get_db()
        first = fetch_and_store(db, fid)
        second = fetch_and_store(db, fid)
    assert first["added"] == 2
    assert second["added"] == 0
    assert second["skipped"] == 2
    with app.app_context():
        n = get_db().execute("SELECT COUNT(*) AS c FROM articles WHERE feed_id = ?", (fid,)).fetchone()["c"]
        assert n == 2


def test_fragment_url_counts_as_duplicate():
    assert canonicalize_url("https://example.com/a1#section") == "https://example.com/a1"
    assert canonicalize_url("not a url") is None
    assert canonicalize_url("") is None


def test_malformed_feed_returns_error(app, monkeypatch):
    fid = _make_feed(app)
    monkeypatch.setattr(feed_service, "_fetch_bytes", lambda url, **k: b"this is not xml <<<")
    with app.app_context():
        db = get_db()
        result = fetch_and_store(db, fid)
        feed = feed_service.get_feed(db, fid)
    assert result["status"] == "error"
    assert result["added"] == 0
    assert feed["last_fetch_status"] == "error"
    assert feed["last_error"]


def test_missing_fields_no_crash(app, monkeypatch):
    fid = _make_feed(app, url="https://example.com/odd-test")
    monkeypatch.setattr(feed_service, "_fetch_bytes", lambda url, **k: MISSING_FIELDS_RSS)
    with app.app_context():
        db = get_db()
        result = fetch_and_store(db, fid)
    assert result["status"] == "ok"
    # has-link-no-title (fallback title) + bad-date stored; no-link item skipped.
    assert result["added"] == 2
    assert result["skipped"] == 1
    with app.app_context():
        rows = get_db().execute("SELECT title, url, published_at FROM articles WHERE feed_id = ?", (fid,)).fetchall()
        by_url = {r["url"]: r for r in rows}
        assert by_url["https://example.com/has-link-no-title"]["title"] == "Untitled"
        assert by_url["https://example.com/bad-date"]["published_at"] is None  # invalid date tolerated


def test_network_failure_returns_error(app, monkeypatch):
    fid = _make_feed(app)

    def boom(url, **k):
        raise RuntimeError("Network error while fetching feed: conn refused")

    monkeypatch.setattr(feed_service, "_fetch_bytes", boom)
    with app.app_context():
        result = fetch_and_store(get_db(), fid)
    assert result["status"] == "error"
    assert "Network" in result["error"]


def test_unsafe_urls_blocked():
    for bad in [
        "http://localhost/feed",
        "http://localhost:8000/x",
        "http://127.0.0.1/",
        "http://10.0.0.5/rss",
        "http://192.168.1.1/rss",
        "http://172.16.5.4/rss",
        "http://169.254.169.254/latest",
        "http://[::1]/rss",
        "http://0.0.0.0/rss",
    ]:
        with pytest.raises(ValueError):
            feed_service._ensure_url_safe(bad)
    # Public URLs pass syntactic + literal checks (DNS not exercised here).
    assert feed_service._validate_url("https://example.com/rss") == "https://example.com/rss"
    for bad in ["http://localhost/feed", "http://127.0.0.1/rss"]:
        with pytest.raises(ValueError):
            feed_service._validate_url(bad)


def test_fetch_unsafe_feed_returns_error_without_network(app):
    # Insert directly to bypass create-time validation, then fetch must block.
    with app.app_context():
        db = get_db()
        cur = db.execute("INSERT INTO feeds (url, title) VALUES (?, ?)", ("http://127.0.0.1/rss", "evil"))
        db.commit()
        fid = cur.lastrowid
        result = fetch_and_store(db, fid)
        feed = feed_service.get_feed(db, fid)
    assert result["status"] == "error"
    assert feed["last_fetch_status"] == "error"


def test_redirect_to_private_is_blocked():
    handler = feed_service._SafeRedirectHandler()
    req = urllib.request.Request("https://example.com/feed")
    with pytest.raises(ValueError):
        handler.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1/secret")


def test_missing_feed_raises(app):
    with app.app_context():
        with pytest.raises(ValueError):
            fetch_and_store(get_db(), 99999)


def test_refresh_route_success(app, client, monkeypatch):
    fid = _make_feed(app, url="https://example.com/refresh-test")
    monkeypatch.setattr(feed_service, "_fetch_bytes", lambda url, **k: RSS_SAMPLE)
    res = client.post(f"/feeds/{fid}/refresh")
    assert res.status_code == 200
    assert b"Refreshed" in res.data


def test_refresh_route_missing_feed(client):
    res = client.post("/feeds/99999/refresh")
    assert res.status_code == 404
