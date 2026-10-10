import os

from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from api.routes.auth_routes import bp as auth_bp
from api.routes.health_route import bp as health_bp
from api.routes.profile_routes import bp as profile_bp
from api.routes.recommendation_routes import bp as recommendation_bp
from config.db import DB_CONFIG, get_db

load_dotenv()

app = Flask(__name__)
CORS_ORIGINS = list(dict.fromkeys(
    origin.strip()
    for origin in [
        "http://localhost:8888",
        "http://127.0.0.1:8888",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        *os.getenv("FRONTEND_ORIGINS", "").split(","),
    ]
    if origin.strip()
))
CORS(app, resources={r"/*": {"origins": CORS_ORIGINS}}, supports_credentials=True)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "bijesgym-secret-key")


def ensure_database_ready():
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SHOW TABLES")
        existing_tables = {row[0] for row in cursor.fetchall()}

        if "users" not in existing_tables:
            cursor.execute(
                """
                CREATE TABLE users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    password VARCHAR(255) NOT NULL,
                    full_name VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

        if "member_profiles" not in existing_tables:
            cursor.execute(
                """
                CREATE TABLE member_profiles (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    age INT,
                    gender CHAR(1),
                    height_cm DECIMAL(5,2),
                    weight_kg DECIMAL(5,2),
                    body_fat_percent DECIMAL(5,2),
                    experience_level VARCHAR(50),
                    weekly_frequency VARCHAR(50),
                    session_duration VARCHAR(50),
                    target_primary VARCHAR(100),
                    target_advanced TEXT,
                    target_body_parts TEXT,
                    waist_cm DECIMAL(5,2),
                    hip_cm DECIMAL(5,2),
                    shoulder_width_cm DECIMAL(5,2),
                    arm_length_cm DECIMAL(5,2),
                    leg_length_cm DECIMAL(5,2),
                    inside_foot_length_cm DECIMAL(5,2),
                    torso_length_cm DECIMAL(5,2),
                    physical_condition TEXT,
                    body_part TEXT,
                    limitation TEXT,
                    other_note TEXT,
                    exercise_complexity VARCHAR(50),
                    facilities TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )

        cursor.execute("SHOW COLUMNS FROM member_profiles")
        profile_columns = {row[0] for row in cursor.fetchall()}
        profile_migrations = {
            "target_advanced": "TEXT",
            "target_body_parts": "TEXT",
            "waist_cm": "DECIMAL(5,2)",
            "hip_cm": "DECIMAL(5,2)",
            "shoulder_width_cm": "DECIMAL(5,2)",
            "arm_length_cm": "DECIMAL(5,2)",
            "leg_length_cm": "DECIMAL(5,2)",
            "inside_foot_length_cm": "DECIMAL(5,2)",
            "torso_length_cm": "DECIMAL(5,2)",
            "body_part": "TEXT",
            "limitation": "TEXT",
            "other_note": "TEXT",
        }
        for column, column_type in profile_migrations.items():
            if column not in profile_columns:
                cursor.execute(f"ALTER TABLE member_profiles ADD COLUMN {column} {column_type}")

        if "user_sessions" not in existing_tables:
            cursor.execute(
                """
                CREATE TABLE user_sessions (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    token_hash CHAR(64) NOT NULL UNIQUE,
                    expires_at DATETIME NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_user_sessions_user_id (user_id),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )

        if "member_recommendations" not in existing_tables:
            cursor.execute(
                """
                CREATE TABLE member_recommendations (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL UNIQUE,
                    recommendations JSON NOT NULL,
                    selected_plan JSON NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )

        needs_default_programs = False
        if "recommendation_programs" not in existing_tables:
            cursor.execute(
                """
                CREATE TABLE recommendation_programs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    split_label VARCHAR(255),
                    description TEXT,
                    experience_level INT,
                    target_primary INT,
                    weekly_frequency INT,
                    session_duration INT,
                    physical_condition INT,
                    facilities INT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            needs_default_programs = True

        if "recommendation_programs" in existing_tables:
            cursor.execute("SELECT COUNT(*) FROM recommendation_programs")
            if cursor.fetchone()[0] == 0:
                needs_default_programs = True

        if needs_default_programs:
            default_programs = [
                ("Full Body Longevity & Low Impact", "Full Body | 1–2x", "Latihan ringan dan singkat untuk kebugaran dasar, mobilitas, dan pemulihan.", 1, 1, 1, 1, 1, 1),
                ("Beginner Full Body Foundation", "Full Body | 3x", "Pengenalan gerakan dasar beban dengan mesin dan dumbbell.", 1, 2, 2, 2, 1, 2),
                ("Express Full Body (Hemat Waktu)", "Full Body | 3x singkat", "Sesi padat dengan durasi singkat dan fokus pada gerakan majemuk utama.", 2, 2, 2, 1, 1, 2),
                ("Metabolic Conditioning & Fat Burn", "Full Body + Kardio | 4x", "Kombinasi beban dan kardio interval untuk membakar lemak.", 2, 1, 3, 2, 1, 2),
                ("Joint-Friendly Muscle Builder", "Full Body | 3x low impact", "Pembentukan otot dengan mesin dan cable, minimal dampak tinggi.", 2, 2, 2, 2, 1, 1),
                ("Full Body Strength Foundation", "Full Body | 3x", "Dasar latihan kekuatan dengan barbell dan progresi beban bertahap.", 2, 3, 2, 2, 2, 3),
                ("Upper/Lower Hypertrophy", "Upper/Lower | 4x", "Pembagian atas dan bawah tubuh empat kali seminggu untuk volume otot yang terukur.", 3, 2, 3, 3, 1, 3),
                ("Hypertrophy & Aesthetic Split", "Push/Pull/Legs | 5–6x", "Split frekuensi tinggi dengan volume besar untuk massa dan estetika tubuh.", 3, 2, 4, 3, 1, 4),
                ("Upper/Lower Powerbuilding", "Upper/Lower | 4x", "Gabungan latihan kekuatan dan hipertrofi pada gerakan aksesori.", 3, 3, 3, 3, 2, 3),
                ("Hybrid Athlete Matrix", "Upper/Lower + Kardio | 5–6x", "Latihan beban empat hari ditambah kondisioning, carry dan aerobik.", 3, 4, 4, 3, 2, 4),
                ("Strength & Power", "Strength Split | 4x", "Program intensitas tinggi untuk kekuatan, power, dan performa dasar atletik.", 4, 4, 3, 3, 2, 3),
                ("Advanced Competition", "Split Lanjutan | 5–6x", "Program volume dan intensitas tinggi untuk member lanjutan atau atlet.", 4, 4, 4, 4, 2, 4),
            ]

            cursor.executemany(
                """
                INSERT INTO recommendation_programs (
                    name, split_label, description, experience_level, target_primary,
                    weekly_frequency, session_duration, physical_condition, facilities
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                default_programs,
            )
            conn.commit()
    finally:
        cursor.close()
        conn.close()


ensure_database_ready()

app.register_blueprint(health_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(recommendation_bp)


@app.get("/")
def index():
    return jsonify({"status": "ok", "message": "Bije's Gym backend is running."})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", "5001")))
