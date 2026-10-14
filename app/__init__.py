import logging
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_cors import CORS

from app.config.db import ensure_database_ready
from app.controllers.auth_controller import auth_bp
from app.controllers.generator_controller import generator_bp
from app.controllers.member_recommendation_controller import member_recommendation_bp
from app.controllers.profile_controller import profile_bp
from app.controllers.recommendation_controller import recommendation_bp

load_dotenv()
logger = logging.getLogger(__name__)


def create_app(test_config=None):
    """
    Application Factory for Bije's Gym Flask Application.

    Configures template and static folders relative to the repository root,
    enables CORS for authorized origins, initializes the database tables,
    and registers all controller Blueprints and view routes.
    """
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
        static_url_path="/static",
    )

    # Core configuration
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "bijesgym-secret-key")

    if test_config:
        app.config.update(test_config)

    # CORS configuration
    cors_origins = list(dict.fromkeys(
        origin.strip()
        for origin in [
            "http://localhost:8888",
            "http://127.0.0.1:8888",
            "http://localhost:5500",
            "http://127.0.0.1:5500",
            *os.getenv("FRONTEND_ORIGINS", "").split(","),
        ]
        if origin.strip()
    ))
    CORS(app, resources={r"/*": {"origins": cors_origins}}, supports_credentials=True)

    @app.after_request
    def add_no_store_header(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # Auto-initialize database schema if not in testing mode
    if not app.config.get("TESTING"):
        try:
            ensure_database_ready()
        except Exception as exc:
            logger.warning("Database auto-initialization skipped or failed on startup: %s", exc)

    # Register Controller Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(generator_bp)
    app.register_blueprint(member_recommendation_bp)
    app.register_blueprint(recommendation_bp)

    # System Health API
    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "message": "Bije's Gym backend is running."})

    # Consolidated Frontend Page Views
    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/auth/login")
    @app.get("/login")
    @app.get("/login/login.html")
    @app.get("/auth/login/login.html")
    def login_page():
        return render_template("auth/login.html")

    @app.get("/dashboard")
    @app.get("/dashboard/index.html")
    def dashboard_page():
        return render_template("dashboard/index.html")

    @app.get("/asesmen")
    @app.get("/asesmen/index.html")
    def asesmen_page():
        return render_template("asesmen/index.html")

    @app.get("/recommendation")
    @app.get("/recommendation/index.html")
    def recommendation_page():
        return render_template("recommendation/index.html")

    @app.get("/profile")
    @app.get("/profile/index.html")
    def profile_page():
        return render_template("profile/index.html")

    # Backward compatibility alias for legacy static asset requests
    @app.route("/assets/<path:filename>")
    def legacy_assets(filename):
        return send_from_directory(app.static_folder, filename)

    return app
