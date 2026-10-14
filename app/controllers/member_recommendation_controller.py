import json
import logging

from flask import Blueprint, jsonify, request

try:
    from app.config.db import get_db
    from app.controllers.auth_controller import get_authenticated_user
except ImportError:
    from config.db import get_db
    from controllers.auth_controller import get_authenticated_user

logger = logging.getLogger(__name__)


def _json_value(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _sort_recommendations_descending(recs):
    if not isinstance(recs, list):
        return recs

    def _score(r):
        if not isinstance(r, dict):
            return 0.0
        val = r.get("similarity")
        if val is None and isinstance(r.get("scores"), dict):
            val = r["scores"].get("final")
        if val is None:
            pct = r.get("percent")
            val = float(pct) / 100.0 if pct is not None else 0.0
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    return sorted(recs, key=_score, reverse=True)


def get_member_recommendations():
    user = get_authenticated_user()
    if not user:
        return jsonify({"error": "Silakan masuk untuk melanjutkan."}), 401
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT recommendations, selected_plan
            FROM member_recommendations
            WHERE user_id = %s
            """,
            (user["id"],),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify({"recommendations": [], "selected_plan": None})
        raw_recs = _json_value(row["recommendations"])
        sorted_recs = _sort_recommendations_descending(raw_recs)
        return jsonify({
            "recommendations": sorted_recs,
            "selected_plan": _json_value(row["selected_plan"]),
        })
    except Exception:
        logger.exception("Gagal mengambil rekomendasi member")
        return jsonify({"error": "Rekomendasi gagal dimuat karena kesalahan server."}), 500
    finally:
        cursor.close()
        conn.close()


def save_member_recommendations():
    user = get_authenticated_user()
    if not user:
        return jsonify({"error": "Silakan masuk untuk melanjutkan."}), 401
    payload = request.get_json(silent=True)
    recommendations = payload.get("recommendations") if isinstance(payload, dict) else None
    if not isinstance(recommendations, list):
        return jsonify({"error": "Rekomendasi harus berupa daftar."}), 400
    recommendations = _sort_recommendations_descending(recommendations)
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO member_recommendations (user_id, recommendations)
            VALUES (%s, %s)
            AS incoming
            ON DUPLICATE KEY UPDATE
                recommendations = incoming.recommendations,
                selected_plan = NULL
            """,
            (user["id"], json.dumps(recommendations, ensure_ascii=False)),
        )
        conn.commit()
        return jsonify({"message": "Rekomendasi berhasil disimpan."})
    except Exception:
        conn.rollback()
        logger.exception("Gagal menyimpan rekomendasi member")
        return jsonify({"error": "Rekomendasi gagal disimpan karena kesalahan server."}), 500
    finally:
        cursor.close()
        conn.close()


def save_selected_plan():
    user = get_authenticated_user()
    if not user:
        return jsonify({"error": "Silakan masuk untuk melanjutkan."}), 401
    payload = request.get_json(silent=True)
    selected_plan = payload.get("selected_plan") if isinstance(payload, dict) else None
    if not isinstance(selected_plan, dict):
        return jsonify({"error": "Program pilihan harus berupa objek."}), 400
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO member_recommendations (user_id, recommendations, selected_plan)
            VALUES (%s, %s, %s)
            AS incoming
            ON DUPLICATE KEY UPDATE selected_plan = incoming.selected_plan
            """,
            (user["id"], "[]", json.dumps(selected_plan, ensure_ascii=False)),
        )
        conn.commit()
        return jsonify({"message": "Program pilihan berhasil disimpan."})
    except Exception:
        conn.rollback()
        logger.exception("Gagal menyimpan program pilihan member")
        return jsonify({"error": "Program pilihan gagal disimpan karena kesalahan server."}), 500
    finally:
        cursor.close()
        conn.close()


member_recommendation_bp = Blueprint("member_recommendation", __name__, url_prefix="/api")

member_recommendation_bp.add_url_rule("/recommendations/current", view_func=get_member_recommendations, methods=["GET"])
member_recommendation_bp.add_url_rule("/recommendations/current", view_func=save_member_recommendations, methods=["PUT"])
member_recommendation_bp.add_url_rule("/recommendations/selected", view_func=save_selected_plan, methods=["PUT"])

