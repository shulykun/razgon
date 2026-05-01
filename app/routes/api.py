from flask import Blueprint, request, jsonify

api_bp = Blueprint("api", __name__)


@api_bp.route("/projects", methods=["POST"])
def create_project():
    """Create project from selected Metrika counter and generate report."""
    data = request.json
    # TODO: create Project, fetch data, call agent, save report
    return jsonify({"status": "ok", "project_id": 1})


@api_bp.route("/projects/<int:project_id>/chat", methods=["POST"])
def chat(project_id):
    """Send message to AI agent and return response."""
    data = request.json
    message = data.get("message", "")
    # TODO: load context, call agent, save messages
    return jsonify({"role": "assistant", "text": f"Stub response to: {message}"})
