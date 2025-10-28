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


# ✅ 读取配置（根据 settings.py）
APP_ENV = os.getenv("APP_ENV", "development")
CONFIG = load_config(APP_ENV)
SECRET_KEY = CONFIG.get("SECRET_KEY", "change-me")
JWT_EXPIRE_HOURS = int(CONFIG.get("JWT_EXPIRE_HOURS", 2))  # 默认 2 小时


def register_user(username: str, email: str, password: str):
    """
    注册新用户
    - 如果 users 表不存在则自动创建
    - 检查重复邮箱
    - 哈希密码并写入数据库
    """
    ensure_users_table()

    if not username or not email or not password:
        return None, "Missing fields"

    existing = find_user_by_email(email)
    if existing:
        return None, "Email already registered"

    hashed = generate_password_hash(password)
    user_id = create_user(username, email, hashed)
    return {"user_id": user_id, "email": email, "username": username}, None


def login_user(email: str, password: str):
    """
    用户登录
    - 校验邮箱与密码
    - 生成 JWT 令牌
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
