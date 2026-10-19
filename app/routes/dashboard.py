"""Dashboard routes. Owner: Dhruv."""
from flask import Blueprint, render_template

from app.database.db import get_db
from app.services import feed_service

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    db = get_db()
    feed_count = 0
    article_count = 0
    healthy_feeds = 0
    error_feeds = 0
    pending_feeds = 0
    latest_sync = None
    recent = []
    recent_feeds = []
    categories = []
    error = None

    try:
        feed_count = feed_service.count_feeds(db)
        article_count = feed_service.count_articles(db)

        # Feed health metrics using last_fetch_status and last_fetched_at
        ok_row = db.execute(
            "SELECT COUNT(*) AS c FROM feeds WHERE last_fetch_status = 'ok'"
        ).fetchone()
        healthy_feeds = int(ok_row["c"]) if ok_row else 0

        err_row = db.execute(
            "SELECT COUNT(*) AS c FROM feeds WHERE last_fetch_status = 'error'"
        ).fetchone()
        error_feeds = int(err_row["c"]) if err_row else 0

        pending_feeds = max(0, feed_count - (healthy_feeds + error_feeds))

        latest_row = db.execute(
            "SELECT MAX(last_fetched_at) AS m FROM feeds WHERE last_fetched_at IS NOT NULL"
        ).fetchone()
        latest_sync = latest_row["m"] if latest_row and latest_row["m"] else None

        recent = db.execute(
            "SELECT a.id, a.feed_id, a.title, a.url, a.summary, a.category, "
            "a.published_at, a.created_at, f.title AS feed_title, f.url AS feed_url "
            "FROM articles a LEFT JOIN feeds f ON a.feed_id = f.id "
            "ORDER BY a.id DESC LIMIT 6"
        ).fetchall()

        recent_feeds = db.execute(
            "SELECT id, url, title, last_fetched_at, last_fetch_status, last_error, created_at "
            "FROM feeds ORDER BY id DESC LIMIT 5"
        ).fetchall()

        categories = db.execute(
            "SELECT category, COUNT(*) AS count FROM articles "
            "WHERE category IS NOT NULL AND category != '' AND category != 'uncategorized' "
            "GROUP BY category ORDER BY count DESC LIMIT 6"
        ).fetchall()

    except Exception as exc:
        error = f"Unable to load some dashboard metrics: {exc}"

    return render_template(
        "dashboard.html",
        feed_count=feed_count,
        article_count=article_count,
        healthy_feeds=healthy_feeds,
        error_feeds=error_feeds,
        pending_feeds=pending_feeds,
        latest_sync=latest_sync,
        recent=recent,
        feeds=recent_feeds,
        categories=categories,
        error=error,
    )
