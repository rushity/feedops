# Feed Ingestion (RSS/Atom) — Owner: Rushit

How `fetch_and_store` in `app/services/feed_service.py` turns a registered
feed URL into `articles` rows. Article schema and search/AI contracts are
unchanged; this doc records the ingestion contract for Rushik and Dhruv.

## Entry points

- `fetch_and_store(db, feed_id) -> dict` with keys
  `feed_id / added / skipped / total / status ("ok" | "error") / error`.
  Raises `ValueError` only when the feed id does not exist; every fetch,
  parse, or network problem is captured as `status="error"` with the feed
  row updated — the app never crashes on a bad feed.
- `POST /feeds/<id>/refresh` (`app/routes/feeds.py`) calls it and renders
  `feeds.html` with `message` (success) or `error` (failure). Add-feed
  (`POST /feeds/`) is create-only and never fetches, so it stays fast
  and offline-safe.

## Normalization into the existing article schema

| Article column | Source |
|---|---|
| `feed_id` | parent feed |
| `title` | entry title, fallback `"Untitled"` |
| `url` | canonical link (see below); entries without a usable link are skipped |
| `summary` | entry `summary` → `description` → `content[0].value`, capped at 5000 chars |
| `category` | first tag term, else `"uncategorized"` |
| `published_at` | `published_parsed`/`updated_parsed` as UTC ISO string; invalid dates → NULL |

Feed `title` is refreshed from the parsed feed metadata when present.

## Deduplication

Canonical URL = strip whitespace + remove `#fragment`; non-http(s) links
are treated as missing. Storage uses `INSERT OR IGNORE` on the existing
`articles.url UNIQUE` key, so re-fetching is idempotent (`added=0`).

## Network policy (`_fetch_bytes`)

- 10s timeout (`FETCH_TIMEOUT`), 2MB cap (`MAX_BYTES`, checked against
  `Content-Length` and during chunked read).
- `User-Agent: FeedOps/1.0 (+feed ingestion)`.
- HTTP errors → `RuntimeError("HTTP <code> ...")`; DNS/timeout/refused →
  `RuntimeError("Network error ...")`; both recorded as feed error status.

## SSRF protection

1. `_validate_url` (no DNS, used at create time): scheme must be
   http/https with a hostname; blocks `localhost`, `*.localhost`,
   `*.local`, `*.internal`, `*.lan`, `*.home.arpa`, `*.invalid`, and
   literal private/loopback/link-local/multicast/unspecified/reserved IPs.
2. `_ensure_url_safe` (fetch time): same checks plus DNS resolution of
   the hostname — any resolved IP in a blocked range aborts the fetch.
3. `_SafeRedirectHandler`: revalidates every redirect target the same
   way (max 5 redirects); unsafe hops abort before any bytes are read.

## Feed status columns (additive, nullable)

`feeds.last_fetched_at` (UTC ISO), `feeds.last_fetch_status`
(`"ok"`/`"error"`), `feeds.last_error` (first 500 chars).
Fresh databases get them from `schema.sql`; older files (foundation
`3b69a75`) gain them via `_ensure_feed_fetch_columns()` in
`app/database/db.py`, which runs on startup and in `init-db`. No data
is ever dropped; article/search/dashboard queries are unaffected.

## Template variables for Dhruv's `feeds.html`

`feeds.html` receives `feeds` (rows now include the three status
columns), plus `message` and `error`. Anything built on these names —
success banner, status badges, `last_fetched_at` details, refresh
`POST` to `url_for('feeds.refresh_feed', feed_id=...)`, loading state,
responsive table — keeps working without backend changes. The refresh
endpoint URL and variable names are stable contracts.

## Tests (`tests/test_ingestion.py`, network fully mocked)

Valid RSS, valid Atom, duplicate re-fetch, fragment dedup, malformed
feed, missing title/link, invalid date, network failure, literal-unsafe
URLs, DNS-independent unsafe fetch, redirect-to-private, missing feed
id, refresh route success (200 + banner) and missing feed (404).
