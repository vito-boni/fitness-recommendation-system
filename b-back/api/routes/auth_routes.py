from flask import Blueprint

from controllers.auth_controller import (
    get_current_session,
    login_user,
    logout_user,
    register_user,
)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

bp.add_url_rule("/register", view_func=register_user, methods=["POST"])
bp.add_url_rule("/login", view_func=login_user, methods=["POST"])
bp.add_url_rule("/session", view_func=get_current_session, methods=["GET"])
bp.add_url_rule("/logout", view_func=logout_user, methods=["POST"])
