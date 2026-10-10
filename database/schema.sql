CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
);

CREATE TABLE user_sessions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at DATETIME NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_sessions_user_id (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE member_recommendations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    recommendations JSON NOT NULL,
    selected_plan JSON NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

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
);
