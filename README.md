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

## Demo Seeding System (Development Only)

Populate the database with realistic demonstration data for local testing, UI review, and dashboard visualization:

```powershell
# Populate realistic demo records (idempotent, safe on multiple runs)
python -m flask seed-demo-data

# Safely remove only demo records without affecting user data
python -m flask seed-demo-data --reset-demo
```

### Demonstration Accounts (Development & Testing Only)

| Role | Email | Password | Details |
|---|---|---|---|
| **Admin** | `admin@example.com` | `AdminDemo2026!` | Access to `/admin/` portal, partner review, campaign moderation |
| **Merchant** (Electronics) | `merchant.electronics@example.com` | `MerchantDemo2026!` | Apex Electronics (`/merchant/dashboard`) |
| **Merchant** (Fashion) | `merchant.fashion@example.com` | `MerchantDemo2026!` | Luxe Trendwear (`/merchant/dashboard`) |
| **Merchant** (Home) | `merchant.home@example.com` | `MerchantDemo2026!` | Urban Nest Living (`/merchant/dashboard`) |
| **Merchant** (Books) | `merchant.books@example.com` | `MerchantDemo2026!` | Horizon Books & Edu (`/merchant/dashboard`) |
| **Merchant** (Fitness) | `merchant.fitness@example.com` | `MerchantDemo2026!` | Velocity Athletics (`/merchant/dashboard`) |
| **Consumers** (25 Accounts)| `consumer.01@example.com` ... `consumer.25@example.com` | `ConsumerDemo2026!` | Diverse category preferences, budgets (INR), saved items |

> [!CAUTION]
> Demo accounts use fictional `@example.com` email domains and development-only passwords. Never seed demo data into production databases.

## Tests

```powershell
pytest -v
```

## Structure

- `run.py`, `config.py` — entry point and env-based config (Rushit)
- `app/__init__.py` — app factory, blueprint registration, `/health`
- `app/database/` — `db.py` helper + `schema.sql` (SQLite at `instance/feed.db`)
- `app/routes/` — `dashboard.py` (Dhruv), `feeds.py` (Rushit), `articles.py` + `search.py` (Rushik), `consumer.py`, `merchant.py`, `admin.py`, `auth.py`, `privacy.py`
- `app/services/` — `feed_service.py`, `search_service.py`, `ai_service.py`, `product_service.py`, `partner_service.py`, `personalization_service.py`, `privacy_service.py`, `seeder.py`
- `app/templates/`, `app/static/` — Jinja + vanilla CSS/JS
- `tests/` — health, dashboard, feeds, search, db, auth, merchant/admin, products, personalization, seeding

See `CONTRIBUTING.md` for ownership and Git workflow.
See `docs/ai-groq.md` for Groq AI setup and `docs/feed-ingestion.md` for RSS/Atom ingestion.
See `docs/SCHEDULER_AND_AUTOMATION.md` for background automation and scheduling.

