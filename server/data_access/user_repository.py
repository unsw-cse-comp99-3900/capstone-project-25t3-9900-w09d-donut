# server/data_access/user_repository.py
from typing import Optional, Dict, Any
from storage.sqlite.database import get_connection

# --- Schema init (idempotent) -------------------------------------------------
def ensure_users_table() -> None:
    """Create users table if it doesn't exist. Safe to call multiple times."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)
        conn.commit()

# --- Row factory to dict ------------------------------------------------------
def _dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

# --- CRUD ---------------------------------------------------------------------
def create_user(username: str, email: str, password_hash: str) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, password_hash),
        )
        conn.commit()
        return cur.lastrowid

def find_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        conn.row_factory = _dict_factory
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", (email,))
        return cur.fetchone()

def find_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        conn.row_factory = _dict_factory
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cur.fetchone()
