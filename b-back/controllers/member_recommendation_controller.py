import json
import logging

from flask import jsonify, request

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
        return jsonify({
            "recommendations": _json_value(row["recommendations"]),
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
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO member_recommendations (user_id, recommendations)
            VALUES (%s, %s)
            AS incoming
            ON DUPLICATE KEY UPDATE recommendations = incoming.recommendations
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
