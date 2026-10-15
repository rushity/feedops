import os
import tempfile

import pytest

from app import create_app
from app.database.db import init_db


@pytest.fixture
def app():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app = create_app({"TESTING": True, "DATABASE": path})
    with app.app_context():
        init_db()
        # Seed one article for dashboard/search tests.
        from app.database.db import get_db

        db = get_db()
        cur = db.execute("INSERT INTO feeds (url, title) VALUES (?, ?)", ("https://example.com/rss", "Example"))
        db.execute(
            "INSERT INTO articles (feed_id, title, url, summary, category) VALUES (?, ?, ?, ?, ?)",
            (cur.lastrowid, "Hello FeedOps", "https://example.com/1", "Welcome summary", "general"),
        )
        db.commit()
    yield app
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def client(app):
    return app.test_client()
