"""Feed routes. Owner: Rushit."""
from flask import Blueprint, redirect, render_template, request, url_for

from app.database.db import get_db
from app.services import feed_service

feeds_bp = Blueprint("feeds", __name__, url_prefix="/feeds")


@feeds_bp.route("/", methods=["GET", "POST"])
def feeds():
    db = get_db()
    error = None
    message = None
    if request.method == "POST":
        url = request.form.get("url", "")
        title = request.form.get("title", "")
        try:
            feed_service.create_feed(db, url, title or None)
            return redirect(url_for("feeds.feeds"))
        except ValueError as exc:
            error = str(exc)
    all_feeds = feed_service.list_feeds(db)
    return render_template("feeds.html", feeds=all_feeds, error=error, message=message)


@feeds_bp.route("/<int:feed_id>/refresh", methods=["POST"])
def refresh_feed(feed_id: int):
    db = get_db()
    feed = feed_service.get_feed(db, feed_id)
    if feed is None:
        all_feeds = feed_service.list_feeds(db)
        return render_template("feeds.html", feeds=all_feeds, error="Feed not found.", message=None), 404
    try:
        result = feed_service.fetch_and_store(db, feed_id)
    except ValueError as exc:
        all_feeds = feed_service.list_feeds(db)
        return render_template("feeds.html", feeds=all_feeds, error=str(exc), message=None)
    all_feeds = feed_service.list_feeds(db)
    if result["status"] == "ok":
        message = (
            f"Refreshed '{feed['title']}'. {result['added']} new, "
            f"{result['skipped']} skipped ({result['total']} total)."
        )
        return render_template("feeds.html", feeds=all_feeds, error=None, message=message)
    return render_template("feeds.html", feeds=all_feeds, error=result["error"], message=None)


@feeds_bp.route("/refresh-all", methods=["POST"])
def refresh_all():
    db = get_db()
    result = feed_service.refresh_all_feeds(db)
    all_feeds = feed_service.list_feeds(db)
    message = (
        f"Refreshed {result['success_count']} of {result['total_feeds']} feeds. "
        f"{result['added']} new articles added."
    )
    error = f"Errors on {result['error_count']} feeds: {'; '.join(result['errors'])}" if result["errors"] else None
    return render_template("feeds.html", feeds=all_feeds, error=error, message=message)


@feeds_bp.route("/<int:feed_id>/delete", methods=["POST"])
def delete_feed(feed_id: int):
    db = get_db()
    feed = feed_service.get_feed(db, feed_id)
    if feed is None:
        all_feeds = feed_service.list_feeds(db)
        return render_template("feeds.html", feeds=all_feeds, error="Feed not found.", message=None), 404
    feed_title = feed["title"] or feed["url"]
    feed_service.delete_feed(db, feed_id)
    all_feeds = feed_service.list_feeds(db)
    message = f"Deleted feed '{feed_title}' and removed its articles."
    return render_template("feeds.html", feeds=all_feeds, error=None, message=message)
