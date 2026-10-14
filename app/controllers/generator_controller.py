from flask import Blueprint, jsonify, request

try:
    from app.config.db import get_db
    from app.controllers.auth_controller import get_authenticated_user
    from app.services.limitation_parser import parse_limitations
    from app.services.program_generator import (
        EXPERIENCE_TIERS,
        MAX_SESSION_MINUTES,
        MIN_SESSION_MINUTES,
        RESISTANCE_ROLES,
        TRAINING_AGE_RANK,
        TRAINING_AGE_TIERS,
        Profile,
        base_prescription,
        cosine_profile_exercise,
        derive_primary_target,
        exercise_line,
        filter_exercises,
        generate,
        parse_experience_tier,
        parse_training_age_tier,
        profile_vector,
    )
except ImportError:
    from config.db import get_db
    from controllers.auth_controller import get_authenticated_user
    from services.limitation_parser import parse_limitations
    from services.program_generator import (
        EXPERIENCE_TIERS,
        MAX_SESSION_MINUTES,
        MIN_SESSION_MINUTES,
        RESISTANCE_ROLES,
        TRAINING_AGE_RANK,
        TRAINING_AGE_TIERS,
        Profile,
        base_prescription,
        cosine_profile_exercise,
        derive_primary_target,
        exercise_line,
        filter_exercises,
        generate,
        parse_experience_tier,
        parse_training_age_tier,
        profile_vector,
    )


def _profile_dict_from_db(user_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM member_profiles WHERE user_id = %s ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = cursor.fetchone() or {}
    finally:
        cursor.close()
        conn.close()
    tier = row.get("training_age_tier") or parse_training_age_tier(row.get("experience_level") or row.get("experience"))
    return {
        "training_age_tier": tier,
        "experience": parse_experience_tier(tier, 2),
        "experience_level": row.get("experience_level") or EXPERIENCE_TIERS[TRAINING_AGE_RANK[tier]],
        "days": row.get("weekly_frequency") or 3,
        "session_minutes": row.get("session_duration") or 60,
        "primary_target": row.get("target_primary"),
        "advanced_targets": row.get("target_advanced"),
        "focus_areas": row.get("focus_areas"),
        "target_body_parts": row.get("target_body_parts"),
        "modalities": row.get("modalities"),
        "facilities": row.get("facilities"),
        "physical_condition": row.get("physical_condition") or "0",
        "limitation_story": row.get("limitation_story"),
        "body_part": row.get("body_part"),
        "limitation": row.get("limitation"),
        "other_note": row.get("other_note"),
        "exercise_complexity": row.get("exercise_complexity") or "balanced",
        "cardio_endurance": row.get("cardio_endurance") or 2,
        "body_fat": row.get("body_fat_percent"),
        "body_fat_percent": row.get("body_fat_percent"),
        "ffmi": row.get("ffmi"),
        "wthr": row.get("wthr"),
        "weight": row.get("weight_kg") or 0,
        "height": row.get("height_cm") or 0,
        "gender": row.get("gender") or "",
        "age": row.get("age") or 0,
        "waist_cm": row.get("waist_cm"),
        "hip_cm": row.get("hip_cm"),
        "shoulder_width_cm": row.get("shoulder_width_cm"),
        "arm_length_cm": row.get("arm_length_cm"),
        "leg_length_cm": row.get("leg_length_cm"),
        "inside_foot_length_cm": row.get("inside_foot_length_cm"),
        "torso_length_cm": row.get("torso_length_cm"),
    }


def generate_program_recommendations():
    user = get_authenticated_user()
    if not user:
        return jsonify({"error": "Silakan masuk untuk melanjutkan."}), 401

    payload = request.get_json(silent=True) or {}
    raw_exp = (
        payload.get("training_age_tier")
        if payload.get("training_age_tier") is not None
        else (payload.get("experience") if payload.get("experience") is not None else payload.get("experience_level"))
    )
    try:
        days = int(payload.get("days"))
        minutes = int(payload.get("session_minutes"))
        tier = parse_training_age_tier(raw_exp)
        experience = parse_experience_tier(tier)
    except (TypeError, ValueError, KeyError):
        return jsonify({"error": "Data asesmen tidak lengkap."}), 400

    raw_target = payload.get("primary_target")
    advanced_targets = payload.get("advanced_targets") or []
    if raw_target not in (None, "", 0, "0"):
        try:
            target = int(raw_target)
        except (TypeError, ValueError):
            return jsonify({"error": "Nilai target utama tidak valid."}), 400
    else:
        target = derive_primary_target(advanced_targets)
        if not target:
            return jsonify({"error": "Pilih minimal satu tujuan spesifik latihan."}), 400

    if not (1 <= days <= 6 and MIN_SESSION_MINUTES <= minutes <= MAX_SESSION_MINUTES
            and 1 <= experience <= 6 and 1 <= target <= 4):
        return jsonify({
            "error": (f"Nilai asesmen di luar rentang yang diizinkan "
                      f"(1–6 hari, {MIN_SESSION_MINUTES}–{MAX_SESSION_MINUTES} menit, tingkat pengalaman Rookie–Veteran).")
        }), 400

    try:
        result = generate(payload, top_n=3)
        if "programs" in result and isinstance(result["programs"], list):
            result["programs"].sort(key=lambda p: -float(p.get("scores", {}).get("final", 0)))
            for i, p in enumerate(result["programs"]):
                p["name"] = f"Program {chr(65 + i)}"
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": f"Gagal menyusun program: {exc}"}), 500
    return jsonify(result), 200


def parse_physical_limitations():
    """Pratinjau deteksi keluhan fisik per kalimat untuk ditampilkan langsung pada form asesmen."""
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text") or payload.get("story") or "").strip()
    return jsonify(parse_limitations(text)), 200


def get_exercise_alternatives():
    """Daftar latihan aman per kelompok otot untuk fitur Kustomisasi bersama Personal Trainer di Beranda."""
    user = get_authenticated_user()
    if not user:
        return jsonify({"error": "Silakan masuk untuk melanjutkan."}), 401
    profile_dict = _profile_dict_from_db(user["id"])
    profile = Profile(profile_dict)
    pool, warnings, filt = filter_exercises(profile)
    wvec = profile_vector(profile)
    by_muscle = {}
    for ex in pool:
        if ex["role"] not in RESISTANCE_ROLES:
            continue
        is_main = ex["role"] == "main"
        pr = base_prescription(ex, profile, is_main)
        sim = cosine_profile_exercise(wvec, ex)
        line = exercise_line(ex, pr["sets"], pr["reps"], pr["seconds"], pr["rest"], profile, sim)
        by_muscle.setdefault(ex["primary_muscle"], []).append(line)
    for muscle_list in by_muscle.values():
        muscle_list.sort(key=lambda item: (-item["similarity"], item["name"]))
    return jsonify({
        "alternatives": by_muscle,
        "warnings": warnings,
        "filter": filt,
        "profile": profile.summary(),
    }), 200


generator_bp = Blueprint("generator", __name__, url_prefix="/api")

generator_bp.add_url_rule("/recommendations/generate", view_func=generate_program_recommendations, methods=["POST"])
generator_bp.add_url_rule("/recommendations/limitations/parse", view_func=parse_physical_limitations, methods=["POST"])
generator_bp.add_url_rule("/recommendations/alternatives", view_func=get_exercise_alternatives, methods=["GET"])

