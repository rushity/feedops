# FeedOps — Feed Management Hub

Team: Rushit, Rushik, Dhruv. Target launch: Monday, 19 October 2026.

Unified feed management and intelligence platform. This repo currently holds the
**shared foundation only**: runnable Flask app, health check, minimal dashboard,
SQLite init, safe env config, and stub interfaces for feed ingestion, search and AI.

## Quickstart

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
flask --app run init-db
python run.py
```

Open http://127.0.0.1:5000/ and http://127.0.0.1:5000/health

## Tests

```powershell
pytest -q
```

## Structure

- `run.py`, `config.py` — entry point and env-based config (Rushit)
- `app/__init__.py` — app factory, blueprint registration, `/health`
- `app/database/` — `db.py` helper + `schema.sql` (SQLite at `instance/feed.db`)
- `app/routes/` — `dashboard.py` (Dhruv), `feeds.py` (Rushit), `articles.py` + `search.py` (Rushik)
- `app/services/` — `feed_service.py` (Rushit), `search_service.py` + `ai_service.py` (Rushik stubs)
- `app/templates/`, `app/static/` — Jinja + vanilla CSS/JS
- `tests/` — health, dashboard, feeds, search, db

See `CONTRIBUTING.md` for ownership and Git workflow.
See `docs/ai-groq.md` for Groq AI setup and `docs/feed-ingestion.md` for RSS/Atom ingestion.
