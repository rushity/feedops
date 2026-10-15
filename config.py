import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration. Safe defaults for local development.

    Owner: Rushit
    All secrets must come from environment variables / .env (never committed).
    """

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    DATABASE = os.environ.get(
        "DATABASE_PATH",
        os.path.join(BASE_DIR, "instance", "feed.db"),
    )
    TESTING = False


class TestingConfig(Config):
    """Configuration used by the automated test suite."""

    TESTING = True
    # Use a temp file set by tests via test_config override; default to memory.
    DATABASE = ":memory:"
