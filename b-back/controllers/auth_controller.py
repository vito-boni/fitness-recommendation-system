import hashlib
import logging
import secrets
from datetime import datetime, timedelta

from flask import jsonify, make_response, request
from werkzeug.security import check_password_hash, generate_password_hash

from config.db import get_db

logger = logging.getLogger(__name__)
SESSION_COOKIE = "bijesgym_session"
SESSION_DURATION = timedelta(days=7)


def _session_token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_session(cursor, user_id):
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + SESSION_DURATION
    cursor.execute(
        """
        INSERT INTO user_sessions (user_id, token_hash, expires_at)
        VALUES (%s, %s, %s)
        """,
        (user_id, _session_token_hash(token), expires_at),
    )
    return token


def _user_payload(user):
    return {
        "id": user["id"],
        "username": user["username"],
        "name": user.get("full_name") or user["username"],
    }


def get_authenticated_user():
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT u.id, u.username, u.full_name
            FROM user_sessions AS s
            JOIN users AS u ON u.id = s.user_id
            WHERE s.token_hash = %s AND s.expires_at > NOW()
            """,
            (_session_token_hash(token),),
        )
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()


def register_user():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or "").strip()
    username = str(payload.get("username") or "").strip()
    password = payload.get("password")
    if not name or not username or not isinstance(password, str) or len(password) < 8:
        return jsonify({"error": "Nama, username, dan kata sandi minimal 8 karakter wajib diisi."}), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            INSERT INTO users (username, password, full_name)
            VALUES (%s, %s, %s)
            """,
            (username, generate_password_hash(password), name),
        )
        user_id = cursor.lastrowid
        user = {"id": user_id, "username": username, "full_name": name}
        token = _create_session(cursor, user_id)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if getattr(exc, "errno", None) == 1062:
            return jsonify({"error": "Username sudah digunakan."}), 409
        logger.exception("Gagal mendaftarkan pengguna")
        return jsonify({"error": "Pendaftaran gagal karena kesalahan server."}), 500
    finally:
        cursor.close()
        conn.close()

    response = make_response(jsonify({"user": _user_payload(user)}), 201)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_DURATION.total_seconds()),
        httponly=True,
        secure=request.is_secure,
        samesite="Lax",
        path="/",
    )
    return response


def login_user():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip()
    password = payload.get("password")
    if not username or not isinstance(password, str) or not password:
        return jsonify({"error": "Username dan kata sandi wajib diisi."}), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, username, password, full_name FROM users WHERE username = %s",
            (username,),
        )
        user = cursor.fetchone()
        if not user or not check_password_hash(user["password"], password):
            return jsonify({"error": "Username atau kata sandi salah."}), 401
        token = _create_session(cursor, user["id"])
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Gagal memproses login")
        return jsonify({"error": "Login gagal karena kesalahan server."}), 500
    finally:
        cursor.close()
        conn.close()

    response = make_response(jsonify({"user": _user_payload(user)}))
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_DURATION.total_seconds()),
        httponly=True,
        secure=request.is_secure,
        samesite="Lax",
        path="/",
    )
    return response


def get_current_session():
    try:
        user = get_authenticated_user()
    except Exception:
        logger.exception("Gagal memeriksa sesi pengguna")
        return jsonify({"error": "Sesi gagal diperiksa karena kesalahan server."}), 500
    if not user:
        return jsonify({"error": "Sesi tidak valid atau sudah berakhir."}), 401
    return jsonify({"user": _user_payload(user)})


def logout_user():
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM user_sessions WHERE token_hash = %s",
                (_session_token_hash(token),),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("Gagal menghapus sesi pengguna")
            return jsonify({"error": "Logout gagal karena kesalahan server."}), 500
        finally:
            cursor.close()
            conn.close()

    response = make_response(jsonify({"message": "Berhasil keluar."}))
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="Lax")
    return response
