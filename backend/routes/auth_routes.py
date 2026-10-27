from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from models.user import User
import json

auth = Blueprint("auth", __name__)

@auth.route("/register", methods=["POST"])
def register():
    data = request.json
    existing_user = User.query.filter_by(username=data["username"]).first()
    if existing_user:
        return jsonify({"error": "Username already exists"}), 400

    hashed_pw = generate_password_hash(data["password"])
    user = User(username=data["username"], email=data["email"], password_hash=hashed_pw)
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "User registered successfully"})

from flask_jwt_extended import create_access_token

@auth.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    if not data or "password" not in data or ("username" not in data and "email" not in data):
        return jsonify({
            "success": False,
            "error": "Missing username/email or password"
        }), 400

    if "username" in data:
        user = User.query.filter_by(username=data["username"]).first()
    else:
        user = User.query.filter_by(email=data["email"]).first()

    if not user:
        return jsonify({
            "success": False,
            "error": "User not found"
        }), 404

    if not check_password_hash(user.password_hash, data["password"]):
        return jsonify({
            "success": False,
            "error": "Invalid password"
        }, 401)

    token = create_access_token(identity=str(user.id))

    return jsonify({
        "success": True,
        "message": "Login successful",
        "access_token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "total_score": user.total_score,
            "current_streak": user.current_streak
        }
    }), 200


from flask_jwt_extended import jwt_required, get_jwt_identity

@auth.route("/profile", methods=["GET"])
@jwt_required()
def profile():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    # return full user dict including module lists
    return jsonify(user.to_dict()), 200


# allow updating profile fields including module lists
@auth.route("/profile", methods=["POST"])
@jwt_required()
def update_profile():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    body = request.get_json(silent=True) or {}
    # fallback: if client didn't send Content-Type, try to parse raw body
    if not body:
        try:
            raw = request.data.decode('utf-8') if request.data else ''
            if raw:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    body = parsed
        except Exception:
            body = {}
    updated = {}

    # update username/email (unique checks)
    if "username" in body:
        new_username = (body.get("username") or "").strip()
        if new_username and new_username != user.username:
            if User.query.filter_by(username=new_username).first():
                return jsonify({"msg": "username already taken"}), 400
            user.username = new_username
            updated["username"] = new_username

    if "email" in body:
        new_email = (body.get("email") or "").strip()
        if new_email and new_email != user.email:
            if User.query.filter_by(email=new_email).first():
                return jsonify({"msg": "email already taken"}), 400
            user.email = new_email
            updated["email"] = new_email

    # update password
    if "password" in body:
        pw = body.get("password")
        if pw:
            user.password_hash = generate_password_hash(pw)
            updated["password"] = "changed"

    # allow updating total_score directly (numeric)
    if "total_score" in body:
        try:
            user.total_score = int(body.get("total_score"))
            updated["total_score"] = user.total_score
        except Exception:
            return jsonify({"msg": "total_score must be a number"}), 400

    # update modules lists (expect arrays)
    for key in ("modules_in_progress", "completed_modules"):
        if key in body:
            val = body.get(key)
            if not isinstance(val, list):
                return jsonify({"msg": f"{key} must be an array/list"}), 400
            # store as JSON text
            setattr(user, key, json.dumps(val))
            updated[key] = val

    db.session.add(user)
    db.session.commit()

    return jsonify({"msg": "profile updated", "updated": updated, "user": user.to_dict()}), 200
