import json
import logging

from flask import Blueprint, jsonify, make_response, request

try:
    from app.config.db import get_db
    from app.controllers.auth_controller import get_authenticated_user
    from app.services.program_generator import (
        EXPERIENCE_TIERS,
        TRAINING_AGE_RANK,
        calculate_body_composition,
        parse_training_age_tier,
    )
except ImportError:
    from config.db import get_db
    from controllers.auth_controller import get_authenticated_user
    from services.program_generator import (
        EXPERIENCE_TIERS,
        TRAINING_AGE_RANK,
        calculate_body_composition,
        parse_training_age_tier,
    )

logger = logging.getLogger(__name__)

PROFILE_FIELDS = (
    "age",
    "gender",
    "height_cm",
    "weight_kg",
    "body_fat_percent",
    "training_age_tier",
    "ffmi",
    "wthr",
    "experience_level",
    "weekly_frequency",
    "session_duration",
    "target_primary",
    "target_advanced",
    "target_body_parts",
    "waist_cm",
    "hip_cm",
    "shoulder_width_cm",
    "arm_length_cm",
    "leg_length_cm",
    "inside_foot_length_cm",
    "torso_length_cm",
    "physical_condition",
    "body_part",
    "limitation",
    "other_note",
    "limitation_story",
    "cardio_endurance",
    "focus_areas",
    "modalities",
    "exercise_complexity",
    "facilities",
)
JSON_FIELDS = {"target_advanced", "target_body_parts", "focus_areas", "modalities", "facilities"}


def _authorized_user(username):
    user = get_authenticated_user()
    if not user:
        return None, (jsonify({"error": "Silakan masuk untuk melanjutkan."}), 401)
    if user["username"] != username:
        return None, (jsonify({"error": "Tidak diizinkan mengakses profil ini."}), 403)
    return user, None


def get_profile(username):
    try:
        user, error_response = _authorized_user(username)
        if error_response:
            return error_response
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM member_profiles WHERE user_id = %s ORDER BY id DESC LIMIT 1",
                (user["id"],),
            )
            profile = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
        if not profile:
            return jsonify({"username": username, "name": user.get("full_name") or username})
        profile["username"] = username
        profile["name"] = user.get("full_name") or username
        return jsonify(profile)
    except Exception:
        logger.exception("Gagal mengambil profil")
        return jsonify({"error": "Profil gagal dimuat karena kesalahan server."}), 500


def upsert_profile(username):
    try:
        user, error_response = _authorized_user(username)
        if error_response:
            return error_response
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Data profil harus berupa objek JSON."}), 400

        values = {}
        for field in PROFILE_FIELDS:
            if field not in payload:
                continue
            value = payload[field]
            if value == "":
                value = None
            if field in JSON_FIELDS and value is not None and not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False)
            values[field] = value

        raw_exp = values.get("training_age_tier") or values.get("experience_level")
        if raw_exp is not None:
            tier = parse_training_age_tier(raw_exp)
            values["training_age_tier"] = tier
            values["experience_level"] = EXPERIENCE_TIERS[TRAINING_AGE_RANK[tier]]

        if values.get("weight_kg") and values.get("height_cm"):
            comp = calculate_body_composition(
                values.get("weight_kg"),
                values.get("height_cm"),
                values.get("body_fat_percent"),
                values.get("waist_cm"),
                values.get("gender") or "L",
                values.get("age"),
            )
            values["ffmi"] = comp["ffmi"]
            values["wthr"] = comp["wthr"]

        new_full_name = str(payload.get("name") or "").strip() if "name" in payload else None
        if not values and not new_full_name:
            return jsonify({"error": "Tidak ada data profil untuk disimpan."}), 400

        conn = get_db()
        cursor = conn.cursor()
        try:
            if new_full_name:
                cursor.execute(
                    "UPDATE users SET full_name = %s WHERE id = %s",
                    (new_full_name, user["id"]),
                )
            if values:
                cursor.execute(
                    "SELECT id FROM member_profiles WHERE user_id = %s ORDER BY id DESC LIMIT 1",
                    (user["id"],),
                )
                existing = cursor.fetchone()
                if existing:
                    assignments = ", ".join(f"{field} = %s" for field in values)
                    cursor.execute(
                        f"UPDATE member_profiles SET {assignments} WHERE id = %s",
                        (*values.values(), existing[0]),
                    )
                else:
                    fields = ["user_id", *values]
                    placeholders = ", ".join(["%s"] * len(fields))
                    cursor.execute(
                        f"INSERT INTO member_profiles ({', '.join(fields)}) VALUES ({placeholders})",
                        (user["id"], *values.values()),
                    )
            conn.commit()
        finally:
            cursor.close()
            conn.close()
        return jsonify({
            "message": "Profil berhasil disimpan.",
            "username": username,
            "ffmi": values.get("ffmi"),
            "wthr": values.get("wthr"),
            "training_age_tier": values.get("training_age_tier"),
            "experience_level": values.get("experience_level"),
            "body_fat_percent": values.get("body_fat_percent"),
        })
    except Exception:
        logger.exception("Gagal menyimpan profil")
        return jsonify({"error": "Profil gagal disimpan karena kesalahan server."}), 500


def delete_profile(username):
    """Hapus akun member dan seluruh data terkait secara permanen."""
    try:
        user, error_response = _authorized_user(username)
        if error_response:
            return error_response
        user_id = user["id"]
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM member_recommendations WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM member_profiles WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("Gagal menghapus akun pengguna")
            return jsonify({"error": "Akun gagal dihapus karena kesalahan server."}), 500
        finally:
            cursor.close()
            conn.close()

        response = make_response(jsonify({"message": "Akun dan semua data terkait berhasil dihapus secara permanen."}))
        response.delete_cookie("bijesgym_session", path="/", samesite="Lax")
        return response
    except Exception:
        logger.exception("Kesalahan saat memproses penghapusan akun")
        return jsonify({"error": "Penghapusan akun gagal karena kesalahan server."}), 500


profile_bp = Blueprint("profile", __name__, url_prefix="/api")

profile_bp.add_url_rule("/profile/<username>", view_func=get_profile, methods=["GET"])
profile_bp.add_url_rule("/profile/<username>", view_func=upsert_profile, methods=["PUT"])
profile_bp.add_url_rule("/profile/<username>", view_func=delete_profile, methods=["DELETE"])

