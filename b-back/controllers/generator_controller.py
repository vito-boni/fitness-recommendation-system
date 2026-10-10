from flask import jsonify, request

from controllers.auth_controller import get_authenticated_user
from services.program_generator import generate


def generate_program_recommendations():
    user = get_authenticated_user()
    if not user:
        return jsonify({"error": "Silakan masuk untuk melanjutkan."}), 401

    payload = request.get_json(silent=True) or {}
    try:
        days = int(payload.get("days"))
        minutes = int(payload.get("session_minutes"))
        experience = int(payload.get("experience"))
        target = int(payload.get("primary_target"))
    except (TypeError, ValueError):
        return jsonify({"error": "Data asesmen tidak lengkap."}), 400
    if not (1 <= days <= 6 and 30 <= minutes <= 180 and 1 <= experience <= 4 and 1 <= target <= 4):
        return jsonify({"error": "Nilai asesmen di luar rentang yang diizinkan."}), 400
    if not payload.get("facilities"):
        return jsonify({"error": "Pilih minimal satu fasilitas."}), 400

    try:
        result = generate(payload, top_n=3)
    except Exception as exc:  # pragma: no cover
        return jsonify({"error": f"Gagal menyusun program: {exc}"}), 500
    return jsonify(result), 200
