"""Dashboard routes. Owner: Dhruv."""
from flask import Blueprint, render_template

from app.database.db import get_db
from app.services import feed_service

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    db = get_db()
    feed_count = feed_service.count_feeds(db)
    article_count = feed_service.count_articles(db)
    recent = db.execute(
        "SELECT id, title, summary, published_at FROM articles ORDER BY id DESC LIMIT 5"
    ).fetchall()
    return render_template(
        "dashboard.html",
        feed_count=feed_count,
        article_count=article_count,
        recent=recent,
    )
