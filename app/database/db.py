"""SQLite helper. Owner: Rushit.

Contract:
- get_db() returns a sqlite3 connection bound to Flask `g`.
- close_db() tears it down.
- init_db() creates tables from schema.sql.
- init_db_if_needed() is safe to call on startup.
- `flask --app run init-db` initialises the DB from the CLI.
"""
import os
import sqlite3

import click
from flask import current_app, g
from flask.cli import with_appcontext



def get_db():
    if "db" not in g:
        db_path = current_app.config["DATABASE"]
        if db_path == ":memory:":
            conn = sqlite3.connect(":memory:")
        else:
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
            conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, encoding="utf-8") as f:
        db.executescript(f.read())
    _ensure_feed_fetch_columns(db)
    _ensure_affiliate_columns(db)
    _ensure_fts_tables(db)
    _ensure_campaign_tables(db)



def _ensure_feed_fetch_columns(db=None):
    """Backward-compatible migration for pre-ingestion databases.

    Fresh DBs already have the columns via schema.sql. Older local DBs
    (created by foundation commit 3b69a75) only have id/url/title/created_at,
    so add the ingestion columns if missing. Additive only - never drops data.
    """
    if db is None:
        db = get_db()
    try:
        cols = {r["name"] for r in db.execute("PRAGMA table_info(feeds)")}
    except Exception:
        return
    if not cols:
        return
    alters = []
    if "last_fetched_at" not in cols:
        alters.append("ALTER TABLE feeds ADD COLUMN last_fetched_at TIMESTAMP")
    if "last_fetch_status" not in cols:
        alters.append("ALTER TABLE feeds ADD COLUMN last_fetch_status TEXT")
    if "last_error" not in cols:
        alters.append("ALTER TABLE feeds ADD COLUMN last_error TEXT")
    for sql in alters:
        db.execute(sql)
    if alters:
        db.commit()


def _ensure_affiliate_columns(db=None):
    """Ensure conversion columns on affiliate_clicks for pre-existing databases."""
    if db is None:
        db = get_db()
    try:
        cols = {r["name"] for r in db.execute("PRAGMA table_info(affiliate_clicks)")}
    except Exception:
        return
    if not cols:
        return
    alters = []
    if "converted" not in cols:
        alters.append("ALTER TABLE affiliate_clicks ADD COLUMN converted INTEGER DEFAULT 0")
    if "conversion_amount" not in cols:
        alters.append("ALTER TABLE affiliate_clicks ADD COLUMN conversion_amount REAL DEFAULT 0.0")
    if "commission_amount" not in cols:
        alters.append("ALTER TABLE affiliate_clicks ADD COLUMN commission_amount REAL DEFAULT 0.0")
    if "order_id" not in cols:
        alters.append("ALTER TABLE affiliate_clicks ADD COLUMN order_id TEXT")
    if "converted_at" not in cols:
        alters.append("ALTER TABLE affiliate_clicks ADD COLUMN converted_at TIMESTAMP")
    for sql in alters:
        db.execute(sql)
    if alters:
        db.commit()


def _ensure_fts_tables(db=None):
    """Ensure products_fts virtual table and sync triggers exist."""
    if db is None:
        db = get_db()
    try:
        tables = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "products" in tables and "products_fts" not in tables:
            db.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
                    title, description, brand, category,
                    content='products', content_rowid='id'
                );
                CREATE TRIGGER IF NOT EXISTS products_ai AFTER INSERT ON products BEGIN
                    INSERT INTO products_fts(rowid, title, description, brand, category)
                    VALUES (new.id, new.title, new.description, new.brand, new.category);
                END;
                CREATE TRIGGER IF NOT EXISTS products_ad AFTER DELETE ON products BEGIN
                    INSERT INTO products_fts(products_fts, rowid, title, description, brand, category)
                    VALUES('delete', old.id, old.title, old.description, old.brand, old.category);
                END;
                CREATE TRIGGER IF NOT EXISTS products_au AFTER UPDATE ON products BEGIN
                    INSERT INTO products_fts(products_fts, rowid, title, description, brand, category)
                    VALUES('delete', old.id, old.title, old.description, old.brand, old.category);
                    INSERT INTO products_fts(rowid, title, description, brand, category)
                    VALUES (new.id, new.title, new.description, new.brand, new.category);
                END;
                INSERT INTO products_fts(rowid, title, description, brand, category)
                SELECT id, title, description, brand, category FROM products;
            """)
            db.commit()
    except Exception:
        pass


def _ensure_campaign_tables(db=None):
    """Ensure campaigns table and indexes exist."""
    if db is None:
        db = get_db()
    try:
        tables = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "campaigns" not in tables:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    partner_id INTEGER NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
                    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    daily_budget REAL DEFAULT 0.0,
                    total_budget REAL DEFAULT 0.0,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    max_impressions_per_user INTEGER DEFAULT 3,
                    status TEXT DEFAULT 'pending',
                    rejection_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_campaigns_partner ON campaigns(partner_id);
                CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
                CREATE INDEX IF NOT EXISTS idx_campaigns_dates ON campaigns(start_date, end_date);
            """)
            db.commit()
    except Exception:
        pass


def init_db_if_needed():
    """Create tables if the DB file is new/empty or missing platform tables. Safe on startup."""
    db_path = current_app.config.get("DATABASE", "")
    needs_init = True
    if db_path != ":memory:" and os.path.exists(db_path) and os.path.getsize(db_path) > 0:
        try:
            db = get_db()
            row = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('feeds','articles','users','products')"
            ).fetchall()
            if len(row) >= 4:
                needs_init = False
        except Exception:
            needs_init = True
    if needs_init:
        init_db()
    else:
        # Tables exist - still ensure ingestion, affiliate, FTS, and campaign tables for older DB files.
        _ensure_feed_fetch_columns()
        _ensure_affiliate_columns()
        _ensure_fts_tables()
        _ensure_campaign_tables()




@click.command("init-db")
@with_appcontext
def init_db_command():
    init_db()
    click.echo("Initialized the database.")


@click.command("refresh-feeds")
@with_appcontext
def refresh_feeds_command():
    """Background feed refresh CLI runner."""
    from app.services import feed_service
    db = get_db()
    result = feed_service.refresh_all_feeds(db)
    click.echo(f"Refreshed {result['success_count']} of {result['total_feeds']} feeds. Added {result['added']} articles.")
    if result["errors"]:
        click.echo(f"Errors ({result['error_count']}): {'; '.join(result['errors'])}")


@click.command("check-price-alerts")
@with_appcontext
def check_price_alerts_command():
    """Check saved products and dispatch price drop alerts."""
    db = get_db()
    prefs = db.execute("SELECT COUNT(*) AS c FROM notification_preferences WHERE price_drop_alerts = 1").fetchone()
    count = prefs["c"] if prefs else 0
    click.echo(f"Price alert monitor checked {count} active subscribers.")


@click.command("seed-demo-data")
@click.option("--reset-demo", is_flag=True, default=False, help="Safely remove only demo records.")
@with_appcontext
def seed_demo_data_command(reset_demo):
    """Seed the database with realistic demonstration data for development."""
    from app.services import seeder
    db = get_db()
    if reset_demo:
        click.echo("Removing demo records from database...")
        res = seeder.reset_all_demo_data(db)
        click.echo("Demo reset complete:")
        for k, v in res.items():
            click.echo(f"  - {k.replace('_', ' ').title()}: {v}")
    else:
        click.echo("Seeding realistic demo data (fixed seed: 42)...")
        res = seeder.seed_all_demo_data(db)
        click.echo("Seeding complete:")
        click.echo(f"  - Users: {res['users_created']} created, {res['users_existing']} existing (1 Admin, 5 Merchants, 25 Consumers)")
        click.echo(f"  - Partners: {res['partners_created']} created, {res['partners_existing']} existing")
        click.echo(f"  - Products: {res['products_created']} created, {res['products_existing']} existing")
        click.echo(f"  - Feeds: {res['feeds_created']} created, {res['feeds_existing']} existing")
        click.echo(f"  - Articles: {res['articles_created']} created, {res['articles_existing']} existing")
        click.echo(f"  - Preferences: {res['preferences_configured']} consumer profiles configured")
        click.echo(f"  - Interactions: {res['saved_items_created']} saved items, {res['feedback_created']} feedback entries")
        click.echo(f"  - Notifications: {res['notifications_created']} events created")
        click.echo(f"  - Affiliate: {res['affiliate_clicks_created']} clicks/conversions tracked")
        click.echo(f"  - Campaigns: {res['campaigns_created']} created, {res['campaigns_existing']} existing")
        click.echo(f"  - Import Jobs: {res['import_jobs_created']} logged")
        click.echo(f"  - Audit Logs: {res['audit_logs_created']} logged")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(refresh_feeds_command)
    app.cli.add_command(check_price_alerts_command)
    app.cli.add_command(seed_demo_data_command)


