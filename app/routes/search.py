"""Search routes. Owner: Rushik (minimal foundation; ranking in milestone 2)."""
from flask import Blueprint, render_template, request

from app.database.db import get_db
from app.services.search_service import search_articles

search_bp = Blueprint("search", __name__, url_prefix="/search")


@search_bp.route("/")
def search():
    query = request.args.get("q", "")
    db = get_db()
    results = search_articles(db, query)
    return render_template("articles.html", articles=results, query=query)
