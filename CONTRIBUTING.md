# Contributing to FeedOps

## File ownership (source of truth)

| Area | Files | Owner |
|------|-------|-------|
| Core / DB / ingestion | `run.py`, `config.py`, `app/__init__.py`, `app/database/db.py`, `app/database/schema.sql`, `app/routes/feeds.py`, `app/services/feed_service.py` | Rushit |
| Search / articles / AI | `app/services/ai_service.py`, `app/services/search_service.py`, `app/routes/articles.py`, `app/routes/search.py`, `app/templates/articles.html`, `app/templates/article_detail.html` | Rushik |
| Dashboard / frontend | `app/routes/dashboard.py`, `app/templates/base.html`, `app/templates/dashboard.html`, `app/templates/feeds.html`, `app/static/css/`, `app/static/js/` | Dhruv |
| Shared (coordinate) | `requirements.txt`, `.env.example`, `.gitignore`, `README.md`, `tests/` | All — discuss in PR |

Do not edit another owner's files without opening an issue/PR and getting review.
Shared contracts (`schema.sql` columns, service function signatures, blueprint names
and URLs `/`, `/feeds/`, `/articles/`, `/search/`, `/health`) must stay stable.
Propose contract changes in a PR before implementing.

## Git workflow

1. `main` is the coordinated branch. Never force-push (`git push --force` forbidden).
2. Create feature branches: `rushit/<topic>`, `rushik/<topic>`, `dhruv/<topic>`.
3. Pull latest `main` before branching. Keep PRs small and focused on owned files.
4. `pytest -q` must pass. Verify no `.env`, `instance/feed.db`, or secrets in `git status` / `git diff`.
5. One review from an owner of touched areas before merge.

## Local setup

Same as `README.md`. Copy `.env.example` to `.env`, never commit `.env`.
Database lives at `instance/feed.db` (gitignored). Run `flask --app run init-db` once.

## Security

Never commit `.env`, `instance/`, API keys or tokens. Use placeholders in `.env.example`.
Never paste secrets in chat or code. Report leaks immediately so tokens can be rotated.
