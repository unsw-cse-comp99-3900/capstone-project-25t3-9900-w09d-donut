from flask import Blueprint, jsonify, request

from server.services.orchestration_service import OrchestrationService

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
