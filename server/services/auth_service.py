# server/services/auth_service.py
from datetime import datetime, timedelta
import os
import jwt
from werkzeug.security import generate_password_hash, check_password_hash

from server.data_access.user_repository import (
    ensure_users_table,
    create_user,
    find_user_by_email,
)
from server.config.settings import load_config


# Load configuration
APP_ENV = os.getenv("APP_ENV", "development")
CONFIG = load_config(APP_ENV)
SECRET_KEY = CONFIG.get("SECRET_KEY", "change-me")
JWT_EXPIRE_HOURS = int(CONFIG.get("JWT_EXPIRE_HOURS", 2))  # default 2 hours


def register_user(username: str, email: str, password: str):
    """
    Register a new user.
    - Ensure the users table exists.
    - Validate uniqueness of the email.
    - Hash the password and persist the record.
    """
    ensure_users_table()

    if not username or not email or not password:
        return None, "Missing fields"

    existing = find_user_by_email(email)
    if existing:
        return None, "Email already registered"

    hashed = generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)
    user_id = create_user(username, email, hashed)
    return {"user_id": user_id, "email": email, "username": username}, None


def login_user(email: str, password: str):
    """
    Authenticate a user and return a JWT token on success.
    """
    ensure_users_table()

    if not email or not password:
        return None, "Missing fields"

    user = find_user_by_email(email)
    if not user:
        return None, "User not found"

    if not check_password_hash(user["password_hash"], password):
        return None, "Invalid password"

    exp = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    token = jwt.encode({"sub": user["email"], "exp": exp}, SECRET_KEY, algorithm="HS256")

    return {"token": token, "email": user["email"]}, None
