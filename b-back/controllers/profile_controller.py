import json
import logging

from flask import jsonify, request

from config.db import get_db
from controllers.auth_controller import get_authenticated_user

logger = logging.getLogger(__name__)

PROFILE_FIELDS = (
    "age",
    "gender",
    "height_cm",
    "weight_kg",
    "body_fat_percent",
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
    "exercise_complexity",
    "facilities",
)
JSON_FIELDS = {"target_advanced", "target_body_parts", "facilities"}


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
        if not values:
            return jsonify({"error": "Tidak ada data profil untuk disimpan."}), 400

        conn = get_db()
        cursor = conn.cursor()
        try:
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
        return jsonify({"message": "Profil berhasil disimpan.", "username": username})
    except Exception:
        logger.exception("Gagal menyimpan profil")
        return jsonify({"error": "Profil gagal disimpan karena kesalahan server."}), 500
