from flask import Blueprint, request, jsonify, session

api_bp = Blueprint("api", __name__)


@api_bp.route("/counters/<counter_id>/goals")
def get_goals(counter_id):
    """Get goals for a Metrika counter."""
    token = session.get("oauth_token")
    # Stub goals (including ecommerce revenue as an option)
    goals = [
        {"id": "ecommerce_revenue", "name": "Доход от интернет-торговли", "type": "ecommerce"},
        {"id": "12345", "name": "Покупка", "type": "action"},
        {"id": "12346", "name": "Регистрация", "type": "action"},
        {"id": "12347", "name": "Отправка формы", "type": "action"},
    ]
    return jsonify(goals)


@api_bp.route("/projects", methods=["POST"])
def create_project():
    """Create project from selected Metrika counter and generate report."""
    data = request.json
    counter_id = data.get("counter_id")
    goal_id = data.get("goal_id")
    # TODO: create Project, fetch data, call agent, save report
    return jsonify({"status": "ok", "project_id": 1})


@api_bp.route("/projects/<int:project_id>/chat", methods=["POST"])
def chat(project_id):
    """Send message to AI agent and return response."""
    data = request.json
    message = data.get("message", "")
    # TODO: load context, call agent, save messages
    return jsonify({"role": "assistant", "text": f"Stub response to: {message}"})
