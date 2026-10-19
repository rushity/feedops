"""Article routes. Owner: Rushik."""
from flask import Blueprint, render_template, request

from app.database.db import get_db
from app.services import ai_service
from app.services.search_service import get_filter_options, search_articles

articles_bp = Blueprint("articles", __name__, url_prefix="/articles")

_LIST_SQL = (
    "SELECT a.id, a.feed_id, a.title, a.url, a.summary, a.category, "
    "a.published_at, a.created_at, "
    "f.title AS feed_title, f.url AS feed_url "
    "FROM articles a LEFT JOIN feeds f ON a.feed_id = f.id "
    "ORDER BY a.id DESC LIMIT 50"
)

_DETAIL_SQL = (
    "SELECT a.id, a.feed_id, a.title, a.url, a.summary, a.category, "
    "a.published_at, a.created_at, "
    "f.title AS feed_title, f.url AS feed_url "
    "FROM articles a LEFT JOIN feeds f ON a.feed_id = f.id "
    "WHERE a.id = ?"
)


def _filters_from_args(args):
    return {
        "q": (args.get("q", "") or "").strip(),
        "source": (args.get("source", "") or "").strip(),
        "category": (args.get("category", "") or "").strip(),
        "date_from": (args.get("date_from", "") or "").strip(),
        "date_to": (args.get("date_to", "") or "").strip(),
    }


@articles_bp.route("/")
def article_list():
    """List recent articles; applies q/source/category/date filters and pagination."""
    import math
    filters = _filters_from_args(request.args)
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    per_page = 20
    offset = (page - 1) * per_page

    db = get_db()
    error = None
    pagination = None
    try:
        if any(filters.values()):
            # Count total matching
            all_matching = search_articles(
                db,
                filters["q"],
                limit=1000,
                source=filters["source"] or None,
                category=filters["category"] or None,
                date_from=filters["date_from"] or None,
                date_to=filters["date_to"] or None,
            )
            total = len(all_matching)
            articles = all_matching[offset:offset + per_page]
        else:
            total_row = db.execute("SELECT COUNT(*) AS c FROM articles").fetchone()
            total = int(total_row["c"]) if total_row else 0
            articles = db.execute(
                "SELECT a.id, a.feed_id, a.title, a.url, a.summary, a.category, "
                "a.published_at, a.created_at, "
                "f.title AS feed_title, f.url AS feed_url "
                "FROM articles a LEFT JOIN feeds f ON a.feed_id = f.id "
                "ORDER BY a.id DESC LIMIT ? OFFSET ?",
                (per_page, offset),
            ).fetchall()

        total_pages = max(1, math.ceil(total / per_page))
        pagination = {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_page": page - 1,
            "next_page": page + 1,
        }
        options = get_filter_options(db)
    except Exception as exc:
        articles, options = [], {"sources": [], "categories": []}
        error = f"Could not load articles: {exc}"
    return render_template(
        "articles.html",
        articles=articles,
        query=filters["q"],
        filters=filters,
        options=options,
        pagination=pagination,
        error=error,
    )


@articles_bp.route("/<int:article_id>")
def article_detail(article_id: int):
    """Detail page with original-source link and on-demand AI analysis."""
    db = get_db()
    article = db.execute(_DETAIL_SQL, (article_id,)).fetchone()
    if article is None:
        return render_template("article_detail.html", article=None), 404

    analysis, analysis_error = None, None
    if request.args.get("analyze") == "1":
        # No DB write: the shared schema has no AI columns, so analysis is
        # computed on demand and displayed only.
        try:
            analysis = ai_service.analyze_article(dict(article))
        except Exception as exc:  # never break reading
            analysis_error = f"AI analysis unavailable: {exc}"

    return render_template(
        "article_detail.html",
        article=article,
        analysis=analysis,
        analysis_error=analysis_error,
        ai_available=ai_service.is_ai_available(),
    )
