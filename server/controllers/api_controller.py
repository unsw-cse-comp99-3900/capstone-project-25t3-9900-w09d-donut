import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file, url_for

from server.data_access.user_repository import ensure_users_table, find_user_by_email
from server.data_access.paper_repository import PaperRepository
from server.data_access.search_history_repository import SearchHistoryRepository
from server.data_access.conversation_repository import ConversationRepository
from server.data_access.summary_repository import SummaryRepository
from server.services.academic_search import AcademicSearchService, search_openalex_papers
from server.services.ai_conversation_service import AIConversationService
from server.services.orchestration_service import OrchestrationService
from server.services.auth_service import register_user, login_user
from ai_agents.services.pdf_builder import SummaryPdfBuilder
from server.services.search_extension_tool import SearchExtensionTool

api_blueprint = Blueprint("api", __name__)

# TODO: Inject real dependencies such as repositories and agent clients
orchestration_service = OrchestrationService()
paper_repository = PaperRepository()
search_history_repository = SearchHistoryRepository()
academic_search_service = AcademicSearchService(
    paper_repository=paper_repository,
    history_repository=search_history_repository,
)
conversation_service = AIConversationService(
    paper_repository=paper_repository,
    history_repository=search_history_repository,
)
conversation_service.register_tool(SearchExtensionTool(academic_search_service))
conversation_repository = ConversationRepository()
summary_repository = SummaryRepository()
summary_pdf_builder = SummaryPdfBuilder()


def _resolve_user_id(payload: dict | None = None) -> int | None:
    payload = payload or {}
    email = (
        request.headers.get("X-User-Email")
        or payload.get("user_email")
        or payload.get("authEmail")
        or payload.get("email")
    )
    if not email:
        token_email = request.headers.get("X-Auth-Email")
        email = token_email or email
    if not email:
        return None

    ensure_users_table()
    user = find_user_by_email(email)
    if not user:
        return None
    return int(user["id"]) if "id" in user else int(user.get("user_id"))


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
        user_id = _resolve_user_id(payload)
        history_id = None
        if user_id is not None:
            history_id, results = academic_search_service.search_and_store(
                user_id=user_id,
                keywords=keywords,
                date_range=date_range,
                concepts=concepts,
                limit=limit,
            )
        else:
            results = search_openalex_papers(
                keywords=keywords,
                date_range=date_range,
                concepts=concepts,
                limit=limit,
            )
        response_payload = {"results": results}
        if history_id is not None:
            response_payload["history_id"] = history_id
        return jsonify(response_payload), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_blueprint.get("/search/history")
def list_search_history():
    user_id = _resolve_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    records = academic_search_service.list_user_history(user_id)
    for record in records:
        record.pop("filters_json", None)
    return jsonify({"history": records}), 200


@api_blueprint.get("/search/history/<int:history_id>")
def get_search_history(history_id: int):
    user_id = _resolve_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    record = academic_search_service.load_history(history_id)
    if not record or record.get("user_id") not in (None, user_id):
        return jsonify({"error": "History not found"}), 404
    record.pop("filters_json", None)
    return jsonify({"history": record}), 200


@api_blueprint.post("/search/history/<int:history_id>/session")
def load_history_session(history_id: int):
    user_id = _resolve_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    record = academic_search_service.load_history(history_id)
    if not record or record.get("user_id") not in (None, user_id):
        return jsonify({"error": "History not found"}), 404

    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    session = conversation_service.load_history_into_session(history_id, session_id=session_id)
    if not session:
        return jsonify({"error": "Unable to load session"}), 500
    return jsonify({
        "session_id": session.session_id,
        "selected_ids": session.selected_ids,
    }), 200


@api_blueprint.post("/search/history/<int:history_id>/selection")
def sync_history_selection(history_id: int):
    user_id = _resolve_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401
    record = academic_search_service.load_history(history_id)
    if not record or record.get("user_id") not in (None, user_id):
        return jsonify({"error": "History not found"}), 404

    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    selected_ids = payload.get("selected_ids")
    if session_id:
        conversation_service.persist_session_selection(history_id, session_id)
        session_record = conversation_repository.get_session(session_id)
        if session_record:
            conversation_repository.upsert_session(
                session_id,
                history_id=history_id,
                user_id=user_id,
                selected_ids=session_record.get("selected_ids") or [],
            )
    elif selected_ids is not None:
        search_history_repository.update_selection(history_id, selected_ids)
        session_record = conversation_repository.find_latest_session_for_history(history_id, user_id)
        if session_record:
            conversation_repository.upsert_session(
                session_record["session_id"],
                history_id=history_id,
                user_id=user_id,
                selected_ids=selected_ids,
            )
    else:
        return jsonify({"error": "Missing selection payload"}), 400
    return jsonify({"detail": "selection updated"}), 200


@api_blueprint.post("/chat/sessions")
def create_chat_session():
    payload = request.get_json(silent=True) or {}
    history_id = payload.get("history_id")
    if not history_id:
        return jsonify({"error": "history_id is required"}), 400

    user_id = _resolve_user_id(payload)
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    history_record = academic_search_service.load_history(history_id)
    if not history_record or history_record.get("user_id") not in (None, user_id):
        return jsonify({"error": "History not found"}), 404

    requested_session_id = payload.get("session_id")
    session_record = None
    if requested_session_id:
        session_record = conversation_repository.get_session(requested_session_id)
        if not session_record or session_record["history_id"] != int(history_id) or session_record.get("user_id") not in (None, user_id):
            return jsonify({"error": "Session not found"}), 404
    else:
        session_record = conversation_repository.find_latest_session_for_history(history_id, user_id)

    if session_record:
        session_id = session_record["session_id"]
    else:
        session_id = requested_session_id or f"chat-{uuid.uuid4().hex}"
        default_selected = [item.get("paper_id") for item in history_record.get("papers", []) if item.get("selected")]
        conversation_repository.upsert_session(session_id, history_id=history_id, user_id=user_id, selected_ids=default_selected)

    session = conversation_service.load_history_into_session(history_id, session_id=session_id)
    if not session:
        return jsonify({"error": "Unable to initialize session"}), 500

    conversation_repository.upsert_session(session_id, history_id=history_id, user_id=user_id, selected_ids=session.selected_ids)
    messages = conversation_repository.list_messages(session_id)

    return jsonify(
        {
            "session_id": session_id,
            "history_id": history_id,
            "selected_ids": session.selected_ids,
            "messages": messages,
        }
    ), 200


@api_blueprint.get("/chat/sessions/<session_id>")
def get_chat_session(session_id: str):
    user_id = _resolve_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    session_record = conversation_repository.get_session(session_id)
    if not session_record or session_record.get("user_id") not in (None, user_id):
        return jsonify({"error": "Session not found"}), 404

    history_id = session_record["history_id"]
    history_record = academic_search_service.load_history(history_id)
    if not history_record or history_record.get("user_id") not in (None, user_id):
        return jsonify({"error": "History not found"}), 404

    try:
        session = conversation_service.ensure_session(history_id, session_id)
        selected_ids = list(session.selected_ids)
    except KeyError:
        selected_ids = session_record.get("selected_ids") or []

    conversation_repository.upsert_session(session_id, history_id=history_id, user_id=user_id, selected_ids=selected_ids)
    messages = conversation_repository.list_messages(session_id)

    return jsonify(
        {
            "session_id": session_id,
            "history_id": history_id,
            "selected_ids": selected_ids,
            "messages": messages,
        }
    ), 200


@api_blueprint.post("/chat/sessions/<session_id>/messages")
def post_chat_message(session_id: str):
    payload = request.get_json(silent=True) or {}
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "message is required"}), 400

    user_id = _resolve_user_id(payload)
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    session_record = conversation_repository.get_session(session_id)
    if not session_record or session_record.get("user_id") not in (None, user_id):
        return jsonify({"error": "Session not found"}), 404

    history_id = session_record["history_id"]
    history_record = academic_search_service.load_history(history_id)
    if not history_record or history_record.get("user_id") not in (None, user_id):
        return jsonify({"error": "History not found"}), 404

    try:
        conversation_service.ensure_session(history_id, session_id)
    except KeyError:
        return jsonify({"error": "Unable to initialize session"}), 500

    try:
        reply = conversation_service.handle_message(session_id, message.strip(), history_id=history_id)
    except Exception as exc:  # pragma: no cover - defensive
        return jsonify({"error": str(exc)}), 500

    conversation_repository.append_messages(
        session_id,
        [
            {"role": "user", "content": message.strip(), "metadata": {"history_id": history_id}},
            {
                "role": "assistant",
                "content": reply.text,
                "metadata": {
                    "citations": reply.citations,
                    "selected_ids": reply.selected_ids,
                    "metadata": reply.metadata,
                },
            },
        ],
    )

    conversation_repository.upsert_session(
        session_id,
        history_id=history_id,
        user_id=user_id,
        selected_ids=reply.selected_ids or [],
    )
    conversation_service.persist_session_selection(history_id, session_id)

    summary_id = None
    pdf_url = None
    summary_type = (reply.metadata or {}).get("summary_type") if reply.metadata else None
    if summary_type:
        focus_aspect = (reply.metadata or {}).get("focus_aspect")
        pdf_path = summary_pdf_builder.build_pdf(
            summary_text=reply.text,
            citations=reply.citations,
            session_id=session_id,
            summary_type=summary_type,
            focus_aspect=focus_aspect,
        )
        summary_id = summary_repository.create_summary(
            history_id=history_id,
            session_id=session_id,
            summary_type=summary_type,
            focus_aspect=focus_aspect,
            summary_text=reply.text,
            pdf_path=str(pdf_path),
        )
        pdf_url = url_for(
            "api.download_summary_pdf",
            session_id=session_id,
            summary_id=summary_id,
            _external=True,
        )

    messages = conversation_repository.list_messages(session_id)
    return jsonify(
        {
            "session_id": session_id,
            "history_id": history_id,
            "reply": reply.text,
            "citations": reply.citations,
            "selected_ids": reply.selected_ids,
            "metadata": reply.metadata,
            "messages": messages,
            "summary_id": summary_id,
            "pdf_url": pdf_url,
        }
    ), 200


@api_blueprint.get("/chat/sessions/<session_id>/summaries")
def list_session_summaries(session_id: str):
    user_id = _resolve_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    session_record = conversation_repository.get_session(session_id)
    if not session_record or session_record.get("user_id") not in (None, user_id):
        return jsonify({"error": "Session not found"}), 404

    summaries = summary_repository.list_by_session(session_id)
    for item in summaries:
        item["pdf_url"] = url_for(
            "api.download_summary_pdf",
            session_id=session_id,
            summary_id=item["id"],
            _external=True,
        )
    return jsonify({"summaries": summaries}), 200


@api_blueprint.get("/chat/sessions/<session_id>/summaries/<int:summary_id>/download")
def download_summary_pdf(session_id: str, summary_id: int):
    user_id = _resolve_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    session_record = conversation_repository.get_session(session_id)
    if not session_record or session_record.get("user_id") not in (None, user_id):
        return jsonify({"error": "Session not found"}), 404

    summary_record = summary_repository.get_summary(summary_id)
    if not summary_record or summary_record["session_id"] != session_id:
        return jsonify({"error": "Summary not found"}), 404

    pdf_path = Path(summary_record["pdf_path"])
    if not pdf_path.exists():
        return jsonify({"error": "Summary PDF is not available"}), 404

    download_name = pdf_path.name
    return send_file(pdf_path, as_attachment=True, download_name=download_name)

@api_blueprint.post("/auth/register")
def register():
    """Register a new user."""
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
    """Authenticate a user and return a JWT token."""
    data = request.get_json() or {}
    email = data.get("email")
    password = data.get("password")

    result, error = login_user(email, password)
    if error:
        code = 404 if error == "User not found" else 401
        return jsonify({"error": error}), code

    return jsonify(result), 200
