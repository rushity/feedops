"""FeedOps entry point. Owner: Rushit."""
import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app

app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_ENV", "development") == "development"
    app.run(host="127.0.0.1", port=5000, debug=debug)
