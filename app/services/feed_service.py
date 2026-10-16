"""Feed service. Owner: Rushit.

Shared contract used by routes/feeds.py and future ingestion jobs:
- list_feeds(db) -> list[Row(id, url, title, last_fetched_at, last_fetch_status, last_error, created_at)]
- get_feed(db, feed_id) -> Row | None (same columns)
- create_feed(db, url, title=None) -> Row (raises ValueError on bad/duplicate URL)
- count_feeds(db) -> int
- count_articles(db) -> int
- fetch_and_store(db, feed_id) -> dict(added/skipped/total/status/error)

RSS/Atom ingestion is offline-safe: network is mocked in tests, all parsing
errors are captured per-feed without crashing the app. Article schema
(feed_id/title/url/summary/category/published_at) is unchanged so Rushik's
article/search modules and Dhruv's dashboard keep working.
"""
import calendar
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

FETCH_TIMEOUT = 10
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5

_FEED_COLUMNS = "id, url, title, last_fetched_at, last_fetch_status, last_error, created_at"


def _validate_url(url: str) -> str:
    """Syntactic validation + literal-IP/hostname SSRF block (no DNS).

    DNS resolution happens at fetch time in _ensure_url_safe so create_feed
    stays offline-safe and existing tests using https://example.com keep passing.
    """
    url = (url or "").strip()
    if not url:
        raise ValueError("Feed URL is required.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Feed URL must start with http:// or https://")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("Feed URL must include a hostname.")
    if _host_is_literal_blocked(host):
        raise ValueError(f"Feed URL target is not allowed: {host}")
    return url


def _host_is_literal_blocked(host: str) -> bool:
    h = host.lower().rstrip(".")
    if h in ("localhost",):
        return True
    for suffix in (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".invalid"):
        if h.endswith(suffix):
            return True
    # Literal IP (v4/v6, brackets already stripped by urlparse.hostname).
    try:
        return _ip_is_blocked(h)
    except ValueError:
        return False


def _ip_is_blocked(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    )


def _resolve_host_ips(host: str):
    try:
        infos = socket.getaddrinfo(host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Feed host could not be resolved (unavailable source): {host}") from exc
    ips = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            ips.append(sockaddr[0])
    if not ips:
        raise ValueError(f"Feed host could not be resolved (unavailable source): {host}")
    return ips


def _ensure_url_safe(url: str) -> str:
    """Full SSRF validation including DNS. Raises ValueError on unsafe/unavailable."""
    clean = _validate_url(url)
    parsed = urlparse(clean)
    host = (parsed.hostname or "").lower()
    # Literal check already done, now resolve names to catch DNS->private.
    try:
        ipaddress.ip_address(host)
        return clean  # literal already checked
    except ValueError:
        pass
    for ip_str in _resolve_host_ips(host):
        try:
            if _ip_is_blocked(ip_str):
                raise ValueError(f"Feed URL resolves to a blocked internal address: {host}")
        except ValueError as exc:
            # _ip_is_blocked raises ValueError only for bad input; re-raise blocks.
            if "blocked internal" in str(exc):
                raise
            raise ValueError(f"Feed URL resolves to an invalid address: {host}") from exc
    return clean


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Revalidates every redirect destination for SSRF. Blocks unsafe hops."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_full = urllib.parse.urljoin(req.full_url, newurl)
        _ensure_url_safe(new_full)  # raises ValueError on unsafe -> aborts fetch
        result = super().redirect_request(req, fp, code, msg, headers, new_full)
        if result is None:
            # Base handler refused (e.g. redirect limit) - surface as an error.
            raise ValueError("Too many redirects or unsupported redirect while fetching feed.")
        return result


def _fetch_bytes(url: str, timeout: int = FETCH_TIMEOUT, max_bytes: int = MAX_BYTES) -> bytes:
    """Fetch a feed URL with timeout, size limit and SSRF-safe redirects."""
    safe_url = _ensure_url_safe(url)
    handler = _SafeRedirectHandler()
    handler.max_redirections = MAX_REDIRECTS
    opener = urllib.request.build_opener(handler)
    req = urllib.request.Request(safe_url, headers={"User-Agent": "FeedOps/1.0 (+feed ingestion)"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            length = resp.headers.get("Content-Length")
            if length:
                try:
                    if int(length) > max_bytes:
                        raise ValueError(f"Feed response too large ({length} bytes).")
                except ValueError as exc:
                    if "too large" in str(exc):
                        raise
                    # Garbage Content-Length header - fall through to chunked read.
            data = bytearray()
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise ValueError(f"Feed response exceeded {max_bytes} byte limit.")
            return bytes(data)
    except ValueError:
        raise
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} while fetching feed.") from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        raise RuntimeError(f"Network error while fetching feed: {exc}") from exc


def canonicalize_url(url: str | None) -> str | None:
    """Stable dedup key: strip whitespace and fragment. Returns None if unusable."""
    if not url:
        return None
    u = url.strip()
    if not u:
        return None
    try:
        base, _frag = urllib.parse.urldefrag(u)
        base = base.strip()
        if not base:
            return None
        parsed = urlparse(base)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None
        return base
    except Exception:
        return None


def _parse_entry_date(entry) -> str | None:
    for key in ("published_parsed", "updated_parsed"):
        try:
            st = entry.get(key)
            if st:
                ts = calendar.timegm(st)
                return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except Exception:
            continue
    return None


def _entry_summary(entry) -> str:
    for key in ("summary", "description"):
        try:
            val = (entry.get(key) or "").strip()
            if val:
                return val[:5000]
        except Exception:
            continue
    try:
        content = entry.get("content")
        if content and isinstance(content, list) and content[0].get("value"):
            return str(content[0]["value"])[:5000]
    except Exception:
        pass
    return ""


def _entry_category(entry) -> str:
    try:
        tags = entry.get("tags") or []
        if tags and isinstance(tags, list):
            term = (tags[0].get("term") or "").strip()
            if term:
                return term[:100]
    except Exception:
        pass
    return "uncategorized"


def list_feeds(db):
    return db.execute(f"SELECT {_FEED_COLUMNS} FROM feeds ORDER BY id DESC").fetchall()


def get_feed(db, feed_id: int):
    return db.execute(f"SELECT {_FEED_COLUMNS} FROM feeds WHERE id = ?", (feed_id,)).fetchone()


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


def _update_fetch_status(db, feed_id: int, status: str, error=None, title=None):
    now = datetime.now(timezone.utc).isoformat()
    err = (str(error)[:500] if error else None)
    if title:
        db.execute(
            "UPDATE feeds SET title = ?, last_fetched_at = ?, last_fetch_status = ?, last_error = ? WHERE id = ?",
            (title[:500], now, status, err, feed_id),
        )
    else:
        db.execute(
            "UPDATE feeds SET last_fetched_at = ?, last_fetch_status = ?, last_error = ? WHERE id = ?",
            (now, status, err, feed_id),
        )
    db.commit()


def fetch_and_store(db, feed_id: int) -> dict:
    """Fetch RSS/Atom for one feed and store new articles. Never crashes the app.

    Returns {"feed_id","added","skipped","total","status","error"} and updates
    feeds.last_fetched_at/last_fetch_status/last_error (+ title when available).
    Raises ValueError only if the feed id does not exist.
    """
    feed = get_feed(db, feed_id)
    if feed is None:
        raise ValueError("Feed not found.")
    feed_url = feed["url"]

    try:
        raw = _fetch_bytes(feed_url)
    except ValueError as exc:  # unsafe URL, too large, DNS failure
        _update_fetch_status(db, feed_id, "error", str(exc))
        return {"feed_id": feed_id, "added": 0, "skipped": 0, "total": 0, "status": "error", "error": str(exc)}
    except RuntimeError as exc:  # HTTP/network errors
        _update_fetch_status(db, feed_id, "error", str(exc))
        return {"feed_id": feed_id, "added": 0, "skipped": 0, "total": 0, "status": "error", "error": str(exc)}
    except Exception as exc:  # pragma: no cover - defensive
        _update_fetch_status(db, feed_id, "error", f"Unexpected fetch error: {exc}")
        return {"feed_id": feed_id, "added": 0, "skipped": 0, "total": 0, "status": "error", "error": str(exc)}

    try:
        import feedparser
    except ImportError as exc:  # pragma: no cover
        _update_fetch_status(db, feed_id, "error", "feedparser is not installed.")
        return {"feed_id": feed_id, "added": 0, "skipped": 0, "total": 0, "status": "error", "error": str(exc)}

    try:
        parsed = feedparser.parse(raw)
    except Exception as exc:
        _update_fetch_status(db, feed_id, "error", f"Could not parse feed: {exc}")
        return {"feed_id": feed_id, "added": 0, "skipped": 0, "total": 0, "status": "error", "error": f"Could not parse feed: {exc}"}

    entries = getattr(parsed, "entries", None) or []
    feed_title = ""
    try:
        feed_title = ((getattr(parsed, "feed", {}) or {}).get("title") or "").strip()
    except Exception:
        feed_title = ""

    if not entries:
        bozo_exc = getattr(parsed, "bozo_exception", None)
        detail = f" ({bozo_exc})" if bozo_exc else ""
        err = f"No entries found or malformed feed{detail}."
        _update_fetch_status(db, feed_id, "error", err, title=feed_title or None)
        return {"feed_id": feed_id, "added": 0, "skipped": 0, "total": 0, "status": "error", "error": err}

    added = 0
    skipped = 0
    for entry in entries:
        try:
            raw_link = entry.get("link") if isinstance(entry, dict) else getattr(entry, "link", None)
            url = canonicalize_url(raw_link)
            if not url:
                skipped += 1
                continue
            raw_title = entry.get("title") if isinstance(entry, dict) else getattr(entry, "title", "")
            title = (str(raw_title).strip() if raw_title else "") or "Untitled"
            summary = _entry_summary(entry)
            category = _entry_category(entry)
            published_at = _parse_entry_date(entry)
            cur = db.execute(
                "INSERT OR IGNORE INTO articles (feed_id, title, url, summary, category, published_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (feed_id, title[:500], url, summary, category, published_at),
            )
            if cur.rowcount and cur.rowcount > 0:
                added += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1
            continue

    db.commit()
    _update_fetch_status(db, feed_id, "ok", None, title=feed_title or None)
    return {"feed_id": feed_id, "added": added, "skipped": skipped, "total": len(entries), "status": "ok", "error": None}
