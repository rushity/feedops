"""Feed service. Owner: Rushit.

Shared contract used by routes/feeds.py and future ingestion jobs:
- list_feeds(db) -> list[Row(id, url, title, created_at)]
- get_feed(db, feed_id) -> Row | None
- create_feed(db, url, title=None) -> Row (raises ValueError on bad/duplicate URL)
- count_feeds(db) -> int
- count_articles(db) -> int

RSS fetching/parsing (fetch_and_store) is intentionally left as a documented
stub for the next milestone so the foundation stays runnable offline.
"""
from urllib.parse import urlparse


def _validate_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("Feed URL is required.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Feed URL must start with http:// or https://")
    return url


def list_feeds(db):
    return db.execute("SELECT id, url, title, created_at FROM feeds ORDER BY id DESC").fetchall()


def get_feed(db, feed_id: int):
    return db.execute("SELECT id, url, title, created_at FROM feeds WHERE id = ?", (feed_id,)).fetchone()


def create_feed(db, url: str, title=None):
    clean_url = _validate_url(url)
    clean_title = (title or "").strip() or clean_url
    try:
        cur = db.execute("INSERT INTO feeds (url, title) VALUES (?, ?)", (clean_url, clean_title))
        db.commit()
    except Exception as exc:
        db.rollback()
        if "UNIQUE" in str(exc).upper():
            raise ValueError("This feed URL is already registered.") from exc
        raise
    return get_feed(db, cur.lastrowid)


def count_feeds(db) -> int:
    row = db.execute("SELECT COUNT(*) AS c FROM feeds").fetchone()
    return int(row["c"]) if row else 0


def count_articles(db) -> int:
    row = db.execute("SELECT COUNT(*) AS c FROM articles").fetchone()
    return int(row["c"]) if row else 0


def fetch_and_store(db, feed_id: int):  # pragma: no cover - future milestone
    """TODO (Rushit, milestone 2): fetch RSS/Atom via feedparser and insert into articles.

    Must be idempotent on article URL (INSERT OR IGNORE) and must not break
    existing schema. See docs/feed-ingestion.md (to be added with milestone 2).
    """
    raise NotImplementedError("RSS fetch will be implemented in milestone 2.")
