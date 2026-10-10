import os
from urllib.parse import urlparse

import mysql.connector
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "mysql://root:root@localhost:8889/bijesgym")
parsed = urlparse(DATABASE_URL)

DB_CONFIG = {
    "host": parsed.hostname or "localhost",
    "port": parsed.port or 8889,
    "user": parsed.username or "root",
    "password": parsed.password or "root",
    "database": parsed.path.lstrip("/") or "bijesgym",
    "autocommit": True,
    "charset": "utf8mb4",
    "raise_on_warnings": True,
}


def get_db():
    conn = mysql.connector.connect(**DB_CONFIG)
    return conn
