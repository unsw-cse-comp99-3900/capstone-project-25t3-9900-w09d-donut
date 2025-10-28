# server/controllers/auth_controller.py
from flask import Blueprint, request, jsonify
from server.services.auth_service import register_user, login_user

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    result, error = register_user(username, email, password)
    if error:
        code = 400 if error != "Email already registered" else 409
        return jsonify({"error": error}), code
    return jsonify({"message": "User registered", "user": result}), 201

@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")

    result, error = login_user(email, password)
    if error:
        code = 404 if error == "User not found" else 401
        return jsonify({"error": error}), code
    return jsonify(result), 200
