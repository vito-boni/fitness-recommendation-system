from flask import Blueprint

from controllers.profile_controller import get_profile, upsert_profile

bp = Blueprint("profile", __name__, url_prefix="/api")

bp.add_url_rule("/profile/<username>", view_func=get_profile, methods=["GET"])
bp.add_url_rule("/profile/<username>", view_func=upsert_profile, methods=["PUT"])
