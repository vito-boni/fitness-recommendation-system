import logging

from flask import Blueprint, jsonify

try:
    from app.config.db import get_db
except ImportError:
    from config.db import get_db

logger = logging.getLogger(__name__)


def get_program_catalog():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT id, name, split_label, description, experience_level,
                   target_primary, weekly_frequency, session_duration,
                   physical_condition, facilities
            FROM recommendation_programs
            WHERE is_active = TRUE
            ORDER BY id
            """
        )
        return jsonify({"programs": cursor.fetchall()})
    except Exception:
        logger.exception("Gagal mengambil katalog program")
        return jsonify({"error": "Katalog program gagal dimuat karena kesalahan server."}), 500
    finally:
        cursor.close()
        conn.close()


recommendation_bp = Blueprint("recommendation", __name__, url_prefix="/api")

recommendation_bp.add_url_rule("/recommendations/programs", view_func=get_program_catalog, methods=["GET"])
