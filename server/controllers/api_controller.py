from flask import Blueprint, jsonify, request

from server.services.orchestration_service import OrchestrationService
from server.services.academic_search import search_openalex_papers as academic_search
from server.services.auth_service import register_user, login_user

api_blueprint = Blueprint("api", __name__)

# TODO: Inject real dependencies such as repositories and agent clients
orchestration_service = OrchestrationService()


@api_blueprint.get("/health")
def healthcheck():
    """Lightweight health probe for uptime checks."""
    return jsonify({"status": "ok"}), 200


@api_blueprint.post("/requests")
def create_research_request():
    payload = request.get_json(silent=True) or {}
    # TODO: Validate payload schema and store initial request metadata
    orchestration_service.plan_research_workflow(payload)
    return jsonify({"detail": "Plan generation queued"}), 202


@api_blueprint.patch("/requests/<request_id>/approval")
def approve_plan(request_id: str):
    payload = request.get_json(silent=True) or {}
    # TODO: Confirm request_id exists and persist approval decision
    orchestration_service.approve_plan(request_id, payload)
    return jsonify({"detail": "Plan approval processing"}), 202


@api_blueprint.get("/requests/<request_id>/draft")
def get_draft(request_id: str):
    # TODO: Retrieve synthesized draft from orchestration service
    draft = orchestration_service.retrieve_draft(request_id)
    return jsonify({"draft": draft}), 200


@api_blueprint.post("/requests/<request_id>/refine")
def refine_draft(request_id: str):
    payload = request.get_json(silent=True) or {}
    # TODO: Validate refinement message and delegate to refinement module
    orchestration_service.refine_draft(request_id, payload)
    return jsonify({"detail": "Refinement request accepted"}), 202

@api_blueprint.post("/normal_search")
def normal_search():
    """
    Invoke academic_search with payload:
    {
      "keywords": ["llm", "retrieval"],
      "date_range": ["2023-01-01", "2024-12-31"] | {"start": "...", "end": "..."} | null,
      "concepts": ["C123", "C456"] | null,
      "limit": 50
    }
    """
    payload = request.get_json(silent=True) or {}

    keywords = payload.get("keywords") or []
    # Normalize date_range to tuple[str, str] | None
    date_range = payload.get("date_range")
    if isinstance(date_range, dict):
        start = date_range.get("start")
        end = date_range.get("end")
        date_range = (start, end) if start and end else None
    elif isinstance(date_range, (list, tuple)) and len(date_range) >= 2:
        date_range = (date_range[0], date_range[1])
    else:
        date_range = None

    concepts = payload.get("concepts") or None
    limit = payload.get("limit", 50)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 50

    try:
        results = academic_search(keywords=keywords, date_range=date_range, concepts=concepts, limit=limit)
        return jsonify({"results": results}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.post("/auth/register")
def register():
    """注册新用户"""
    data = request.get_json() or {}
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    result, error = register_user(username, email, password)
    if error:
        code = 400 if error != "Email already registered" else 409
        return jsonify({"error": error}), code

    return jsonify({"message": "User registered", "user": result}), 201


@api_blueprint.post("/auth/login")
def login():
    """用户登录"""
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")

    result, error = login_user(email, password)
    if error:
        code = 404 if error == "User not found" else 401
        return jsonify({"error": error}), code

    return jsonify(result), 200