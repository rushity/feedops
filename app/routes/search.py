"""Search routes. Owner: Rushik."""
from flask import Blueprint, render_template, request

from app.database.db import get_db
from app.services.search_service import get_filter_options, search_articles

search_bp = Blueprint("search", __name__, url_prefix="/search")


@search_bp.route("/")
def search():
    query = (request.args.get("q", "") or "").strip()
    filters = {
        "q": query,
        "source": (request.args.get("source", "") or "").strip(),
        "category": (request.args.get("category", "") or "").strip(),
        "date_from": (request.args.get("date_from", "") or "").strip(),
        "date_to": (request.args.get("date_to", "") or "").strip(),
    }
    db = get_db()
    error = None
    try:
        results = search_articles(
            db,
            query,
            limit=50,
            source=filters["source"] or None,
            category=filters["category"] or None,
            date_from=filters["date_from"] or None,
            date_to=filters["date_to"] or None,
        )
        options = get_filter_options(db)
    except Exception as exc:
        results, options = [], {"sources": [], "categories": []}
        error = f"Search failed: {exc}"
    return render_template(
        "articles.html",
        articles=results,
        query=query,
        filters=filters,
        options=options,
        error=error,
    )
