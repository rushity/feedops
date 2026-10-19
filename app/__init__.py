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
    from app.routes.auth import auth_bp
    from app.routes.consumer import consumer_bp
    from app.routes.merchant import merchant_bp
    from app.routes.admin import admin_bp
    from app.routes.privacy import privacy_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(feeds_bp)
    app.register_blueprint(articles_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(consumer_bp)
    app.register_blueprint(merchant_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(privacy_bp)

    @app.context_processor
    def inject_user_context():
        from flask import session
        return {
            "current_user_id": session.get("user_id"),
            "current_user_email": session.get("user_email"),
            "current_user_role": session.get("user_role"),
            "current_user_name": session.get("user_name"),
        }

    @app.route("/health")
    def health():
        return jsonify(status="ok", service="feedops"), 200

    return app
