"""Flask application factory for the Document Tracking System."""
import os

from flask import Flask, jsonify, render_template, request

from .config import DevelopmentConfig, ProductionConfig, TestingConfig, Config


def create_app(config_name: str = "") -> Flask:
    """Create and configure the Flask app.

    config_name: development | testing | production (default: FLASK_ENV env
    variable, falling back to development).
    """
    config_name = config_name or os.environ.get("FLASK_ENV", "development")

    if config_name in ("testing", "test"):
        cfg = TestingConfig
    elif config_name in ("production", "prod"):
        cfg = ProductionConfig()
    else:
        cfg = DevelopmentConfig if config_name in ("development", "dev") else Config

    app = Flask(__name__)
    app.config["CFG"] = cfg
    # Flask session interface reads these under its own names:
    app.config["SECRET_KEY"] = cfg.SECRET_KEY
    app.config["UPLOAD_FOLDER"] = cfg.UPLOAD_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = cfg.MAX_CONTENT_LENGTH
    app.config["ALLOWED_EXTENSIONS"] = cfg.ALLOWED_EXTENSIONS
    app.config.update(
        SESSION_COOKIE_HTTPONLY=cfg.SESSION_COOKIE_HTTPONLY,
        SESSION_COOKIE_SAMESITE=cfg.SESSION_COOKIE_SAMESITE,
        SESSION_COOKIE_SECURE=cfg.SESSION_COOKIE_SECURE,
        PERMANENT_SESSION_LIFETIME=cfg.PERMANENT_SESSION_LIFETIME,
        TESTING=getattr(cfg, "TESTING", False),
        DEBUG=getattr(cfg, "DEBUG", False),
    )

    from .auth.routes import auth_bp
    from .documents.routes import documents_bp
    from .approvals.routes import approvals_bp
    from .dashboard.routes import dashboard_bp
    from .reports.routes import reports_bp
    from .notifications.routes import notifications_bp
    from .admin.routes import admin_bp
    from .services.csrf import csrf_protect
    from .services.helpers import register_context_and_filters
    from .db import close_db

    for bp in (auth_bp, documents_bp, approvals_bp, dashboard_bp,
               reports_bp, notifications_bp, admin_bp):
        app.register_blueprint(bp)

    app.before_request(csrf_protect)
    register_context_and_filters(app)
    app.teardown_appcontext(close_db)

    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found"), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(_e):
        if request.path.startswith("/api/"):
            return jsonify(error="Forbidden"), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(400)
    def bad_request(_e):
        if request.path.startswith("/api/"):
            return jsonify(error="Bad request"), 400
        return render_template("errors/400.html"), 400

    @app.errorhandler(413)
    def too_large(_e):
        return render_template("errors/400.html",
                               message="The uploaded file exceeds the size limit."), 413

    @app.errorhandler(500)
    def server_error(_e):
        if request.path.startswith("/api/"):
            return jsonify(error="Internal server error"), 500
        return render_template("errors/500.html"), 500

    @app.route("/healthz")
    def healthz():
        """Health probe: reports whether MySQL is reachable."""
        from . import db
        try:
            db.ping()
            return jsonify(status="ok", database="up")
        except Exception:
            return jsonify(status="degraded", database="down"), 503

    return app
