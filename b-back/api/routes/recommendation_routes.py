from flask import Blueprint

from controllers.generator_controller import generate_program_recommendations
from controllers.member_recommendation_controller import (
    get_member_recommendations,
    save_member_recommendations,
    save_selected_plan,
)
from controllers.recommendation_controller import get_program_catalog

bp = Blueprint("recommendation", __name__, url_prefix="/api")

bp.add_url_rule("/recommendations/programs", view_func=get_program_catalog, methods=["GET"])
bp.add_url_rule("/recommendations/generate", view_func=generate_program_recommendations, methods=["POST"])
bp.add_url_rule("/recommendations/current", view_func=get_member_recommendations, methods=["GET"])
bp.add_url_rule("/recommendations/current", view_func=save_member_recommendations, methods=["PUT"])
bp.add_url_rule("/recommendations/selected", view_func=save_selected_plan, methods=["PUT"])
