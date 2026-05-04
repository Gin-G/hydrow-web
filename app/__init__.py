import logging
import os

from flask import Flask
from flask_session import Session

# Silence third-party loggers — credentials must never appear in logs
for name in ("werkzeug", "urllib3", "requests"):
    lg = logging.getLogger(name)
    lg.setLevel(logging.CRITICAL)
    lg.handlers = []
    lg.propagate = False


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # ── Secret key (required for session signing) ─────────────────────────────
    app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]

    # ── Server-side sessions backed by Redis ──────────────────────────────────
    app.config["SESSION_TYPE"] = "redis"
    app.config["SESSION_PERMANENT"] = False
    app.config["SESSION_USE_SIGNER"] = True          # HMAC-sign the cookie id
    app.config["SESSION_KEY_PREFIX"] = "hydrow:"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SECURE_COOKIE", "true").lower() == "true"

    # Redis connection — injected via environment variable
    import redis
    app.config["SESSION_REDIS"] = redis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    )

    Session(app)

    # Suppress app logger output
    app.logger.setLevel(logging.CRITICAL)

    # ── Register blueprints ───────────────────────────────────────────────────
    from .routes import main
    app.register_blueprint(main)

    return app