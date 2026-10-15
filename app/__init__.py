"""FeedOps Flask application factory. Owner: Rushit."""
import os

from flask import Flask, jsonify

from config import Config


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    # Ensure the folder for instance/feed.db exists (unless :memory:).
    db_path = app.config.get("DATABASE", "")
    if db_path != ":memory:" and db_path:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    from app.database.db import init_app

    init_app(app)

    # Auto-create tables on first run for local dev (no-op if they exist).
    with app.app_context():
        from app.database.db import init_db_if_needed

        init_db_if_needed()

    # Register blueprints (contracts owned per CONTRIBUTING.md).
    from app.routes.dashboard import dashboard_bp
    from app.routes.feeds import feeds_bp
    from app.routes.articles import articles_bp
    from app.routes.search import search_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(feeds_bp)
    app.register_blueprint(articles_bp)
    app.register_blueprint(search_bp)

    @app.route("/health")
    def health():
        return jsonify(status="ok", service="feedops"), 200

    return app
