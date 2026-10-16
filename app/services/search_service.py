"""Search service. Owner: Rushik.

Contract (stable — other modules import these names):
- search_articles(db, query, limit=20) -> list[Row]
  Searches title/summary with LIKE (case-insensitive). Empty query
  with no filters -> [].
- get_filter_options(db) -> {"sources": [...], "categories": [...]}

Extended (backward-compatible keyword filters, same single-query path):
- search_articles(db, query, limit=20, *, source=None, category=None,
                   date_from=None, date_to=None, offset=0)

Notes:
- Uses only `?` placeholders (parameter-bound, injection-safe).
- LIKE wildcards in user input are escaped so `%`/`_` match literally.
- `source` matches the parent feed's title or URL (exact, case-insensitive).
- `published_at` is TEXT in the shared schema; date filters compare ISO strings.
- One query only; no repeated processing. No schema changes.
"""

from datetime import datetime

MAX_LIMIT = 100
DEFAULT_LIMIT = 20


def _escape_like(text):
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _parse_date(value):
    """Accept YYYY-MM-DD or full ISO strings; return normalized string or None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            datetime.strptime(text, "%Y-%m-%d")
            return text
        # Full ISO: normalize to YYYY-MM-DD for TEXT comparison.
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _clamp_limit(limit):
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    return min(max(limit, 1), MAX_LIMIT)


def _clamp_offset(offset):
    try:
        offset = int(offset)
    except (TypeError, ValueError):
        offset = 0
    return max(offset, 0)


def search_articles(db, query, limit=20, *, source=None, category=None,
                    date_from=None, date_to=None, offset=0):
    q = (query or "").strip()
    src = (source or "").strip() if isinstance(source, str) else source
    cat = (category or "").strip() if isinstance(category, str) else category
    if src == "":
        src = None
    if cat == "":
        cat = None

    # Preserve the original contract: bare empty search returns [].
    if not q and src is None and cat is None and not date_from and not date_to:
        return []

    limit = _clamp_limit(limit)
    offset = _clamp_offset(offset)

    where = []
    params = []

    if q:
        like = f"%{_escape_like(q)}%"
        where.append("(a.title LIKE ? ESCAPE '\\' OR a.summary LIKE ? ESCAPE '\\')")
        params.extend([like, like])

    if src is not None:
        where.append("(f.title = ? COLLATE NOCASE OR f.url = ? COLLATE NOCASE)")
        params.extend([src, src])

    if cat is not None:
        where.append("a.category = ? COLLATE NOCASE")
        params.append(cat)

    dt_from = _parse_date(date_from)
    if dt_from is not None:
        where.append("a.published_at >= ?")
        params.append(dt_from)

    dt_to = _parse_date(date_to)
    if dt_to is not None:
        where.append("a.published_at <= ?")
        params.append(dt_to)

    sql = (
        "SELECT a.id, a.feed_id, a.title, a.url, a.summary, a.category, "
        "a.published_at, a.created_at, "
        "f.title AS feed_title, f.url AS feed_url "
        "FROM articles a LEFT JOIN feeds f ON a.feed_id = f.id"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY a.id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    return db.execute(sql, tuple(params)).fetchall()


def get_filter_options(db):
    """Distinct category / feed-source values for filter dropdowns (2 queries)."""
    cats = [
        r["category"]
        for r in db.execute(
            "SELECT DISTINCT category FROM articles "
            "WHERE category IS NOT NULL AND category != '' "
            "ORDER BY category"
        ).fetchall()
    ]
    sources = [
        r["title"]
        for r in db.execute(
            "SELECT DISTINCT title FROM feeds "
            "WHERE title IS NOT NULL AND title != '' "
            "ORDER BY title"
        ).fetchall()
    ]
    return {"sources": sources, "categories": cats}
