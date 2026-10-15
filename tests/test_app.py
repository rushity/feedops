def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok", "service": "feedops"}


def test_dashboard(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"FeedOps" in res.data


def test_feeds_page_and_add(client):
    assert client.get("/feeds/").status_code == 200
    res = client.post("/feeds/", data={"url": "https://example.com/other", "title": "Other"}, follow_redirects=True)
    assert res.status_code == 200
    assert b"Other" in res.data


def test_feeds_rejects_bad_url(client):
    res = client.post("/feeds/", data={"url": "not-a-url"})
    assert res.status_code == 200
    assert b"http" in res.data.lower()


def test_articles_and_detail(client):
    assert client.get("/articles/").status_code == 200
    assert b"Hello FeedOps" in client.get("/articles/").data
    assert client.get("/articles/1").status_code == 200
    assert client.get("/articles/9999").status_code == 404


def test_search(client):
    res = client.get("/search/?q=Hello")
    assert res.status_code == 200
    assert b"Hello FeedOps" in res.data
    assert client.get("/search/").status_code == 200


def test_db_tables(app):
    with app.app_context():
        from app.database.db import get_db

        db = get_db()
        tables = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"feeds", "articles"} <= tables
