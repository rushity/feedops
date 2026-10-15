"""Feed routes. Owner: Rushit."""
from flask import Blueprint, redirect, render_template, request, url_for

from app.database.db import get_db
from app.services import feed_service

feeds_bp = Blueprint("feeds", __name__, url_prefix="/feeds")


@feeds_bp.route("/", methods=["GET", "POST"])
def feeds():
    db = get_db()
    error = None
    if request.method == "POST":
        url = request.form.get("url", "")
        title = request.form.get("title", "")
        try:
            feed_service.create_feed(db, url, title or None)
            return redirect(url_for("feeds.feeds"))
        except ValueError as exc:
            error = str(exc)
    all_feeds = feed_service.list_feeds(db)
    return render_template("feeds.html", feeds=all_feeds, error=error)
