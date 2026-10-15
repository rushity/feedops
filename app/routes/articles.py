"""Article routes. Owner: Rushik (minimal foundation; full UI in milestone 2)."""
from flask import Blueprint, render_template

from app.database.db import get_db

articles_bp = Blueprint("articles", __name__, url_prefix="/articles")


@articles_bp.route("/")
def article_list():
    db = get_db()
    articles = db.execute(
        "SELECT id, feed_id, title, url, summary, category, published_at "
        "FROM articles ORDER BY id DESC LIMIT 50"
    ).fetchall()
    return render_template("articles.html", articles=articles)


@articles_bp.route("/<int:article_id>")
def article_detail(article_id: int):
    db = get_db()
    article = db.execute(
        "SELECT id, feed_id, title, url, summary, category, published_at "
        "FROM articles WHERE id = ?",
        (article_id,),
    ).fetchone()
    if article is None:
        return render_template("article_detail.html", article=None), 404
    return render_template("article_detail.html", article=article)
