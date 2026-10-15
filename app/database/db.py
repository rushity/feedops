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


def init_db_if_needed():
    """Create tables if the DB file is new/empty. Safe to call on startup."""
    db_path = current_app.config.get("DATABASE", "")
    needs_init = True
    if db_path != ":memory:" and os.path.exists(db_path) and os.path.getsize(db_path) > 0:
        try:
            db = get_db()
            db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='feeds'").fetchone()
            # If query succeeds, check whether tables exist.
            row = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('feeds','articles')"
            ).fetchall()
            if len(row) >= 2:
                needs_init = False
        except Exception:
            needs_init = True
    if needs_init:
        init_db()


@click.command("init-db")
def init_db_command():
    init_db()
    click.echo("Initialized the database.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
