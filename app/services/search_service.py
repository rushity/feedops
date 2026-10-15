"""Search service. Owner: Rushik (stub interface for milestone 2).

Contract:
- search_articles(db, query, limit=20) -> list[Row]
  Searches title/summary with LIKE. Case-insensitive. Empty query -> [].
"""


def search_articles(db, query: str, limit: int = 20):
    q = (query or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    return db.execute(
        """
        SELECT id, feed_id, title, url, summary, category, published_at, created_at
        FROM articles
        WHERE title LIKE ? OR summary LIKE ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (like, like, limit),
    ).fetchall()
