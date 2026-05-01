import json
import threading
from flask import Blueprint, request, jsonify, session
from app import db
from app.models import Project, Report, IntegrationLog
from app.services.report import collect_data, generate_report
from app.services.logger import logged_request

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
    """Create project and start async report generation."""
    data = request.json
    counter_id = data.get("counter_id")
    goal_id = data.get("goal_id")
    objective = data.get("objective", "sales")

    # TODO: get real site name from Metrika
    site_name = f"Сайт #{counter_id}"
    token = session.get("oauth_token", "")

    project = Project(
        site_name=site_name,
        objective=objective,
        metrika_counter_id=counter_id,
        user_id=1,  # TODO: real user
    )
    db.session.add(project)
    db.session.commit()

    report = Report(project_id=project.id, ai_report_text="")
    db.session.add(report)
    db.session.commit()

    # Start background report generation
    thread = threading.Thread(
        target=_generate_report_async,
        args=(project.id, report.id, token, counter_id, goal_id, objective),
    )
    thread.start()

    return jsonify({"status": "ok", "project_id": project.id})


def _generate_report_async(project_id, report_id, token, counter_id, goal_id, objective):
    """Background task: collect data + call agent + save report."""
    from app import create_app
    app = create_app()
    with app.app_context():
        try:
            with logged_request("metrika", "collect_all", project_id=project_id) as log:
                data = collect_data(token, counter_id, host_id=None)
                log.ok(request_url=f"metrika:{counter_id}", response_snippet="OK")
        except Exception as e:
            with app.app_context():
                log_integration = __import__("app.services.logger", fromlist=["log_integration"]).log_integration
                log_integration("metrika", "collect_all", level="error", project_id=project_id, error_message=str(e))
            data = {}

        try:
            with logged_request("agent", "generate_report", project_id=project_id) as log:
                ai_text = generate_report(data, objective=objective)
                log.ok(response_snippet=ai_text[:500] if ai_text else None)
        except Exception as e:
            ai_text = f"Ошибка генерации отчёта: {str(e)}"

        report = db.session.get(Report, report_id)
        report.raw_data = json.dumps(data, ensure_ascii=False) if data else None
        report.ai_report_text = ai_text
        db.session.commit()


@api_bp.route("/projects/<int:project_id>/chat", methods=["POST"])
def chat(project_id):
    """Send message to AI agent and return response."""
    data = request.json
    message = data.get("message", "")
    # TODO: load context, call agent, save messages
    return jsonify({"role": "assistant", "text": f"Stub response to: {message}"})


@api_bp.route("/projects/<int:project_id>/status")
def project_status(project_id):
    """Check if report is ready."""
    report = Report.query.filter_by(project_id=project_id).order_by(Report.id.desc()).first()
    if not report:
        return jsonify({"ready": False})
    ready = bool(report.ai_report_text and not report.ai_report_text.startswith("Ошибка"))
    return jsonify({
        "ready": ready,
        "error": report.ai_report_text.startswith("Ошибка") if report.ai_report_text else False,
        "text": report.ai_report_text or "",
    })


@api_bp.route("/projects/<int:project_id>/logs")
def project_logs(project_id):
    """Get integration logs for a project."""
    logs = IntegrationLog.query.filter_by(project_id=project_id).order_by(IntegrationLog.created_at.desc()).limit(50).all()
    return jsonify([{
        "id": l.id,
        "source": l.source,
        "level": l.level,
        "method": l.method,
        "status_code": l.status_code,
        "error_message": l.error_message,
        "duration_ms": l.duration_ms,
        "created_at": l.created_at.isoformat(),
    } for l in logs])
