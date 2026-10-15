-- FeedOps shared schema. Owner: Rushit.
-- SQLite at instance/feed.db (local dev). Do not commit the .db file.
-- Contracts: feeds <-> articles (articles.feed_id FK). Keep column names stable.

CREATE TABLE IF NOT EXISTS feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id INTEGER REFERENCES feeds(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    url TEXT UNIQUE,
    summary TEXT,
    category TEXT DEFAULT 'uncategorized',
    published_at TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_articles_feed_id ON articles(feed_id);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);
