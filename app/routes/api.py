import json
import logging
import threading
import requests as http_requests
from flask import Blueprint, request, jsonify, session
from app.models import User, Project

OBJECTIVE_LABELS = {"sales": "Увеличить охват и продажи", "optimize": "Сэкономить на рекламе, не потеряв доход", "efficiency": "Поднять эффективность сайта", "audience": "Понять свою аудиторию"}
STANDARD_OBJECTIVES = set(OBJECTIVE_LABELS.keys())

def _get_token():
    """Get OAuth token from session or database."""
    token = session.get("oauth_token")
    if token:
        return token
    user_id = session.get("user_id")
    if user_id:
        user = User.query.get(user_id)
        if user and user.oauth_token:
            session["oauth_token"] = user.oauth_token  # cache in session
            return user.oauth_token
    return None


def _build_goal_text(project):
    """Build goal text from project settings, including custom objective."""
    goal_text = "Составь аналитический отчёт с выводами и рекомендациями."
    if project.metrika_goal_name:
        goal_text += f" Цель: {project.metrika_goal_name}."
    # Add objective as client's task
    if project.objective:
        if project.objective in STANDARD_OBJECTIVES:
            goal_text += f" Задача клиента: {OBJECTIVE_LABELS[project.objective]}."
        else:
            goal_text += f" Задача клиента: {project.objective}."
    if project.comment:
        goal_text += f" {project.comment}"
    return goal_text
from app import db
from app.models import Project, Report, IntegrationLog, ChatMessage
from app.services.report import collect_data
from app.services.logger import logged_request
from app.agent.client import send_project_init, send_chat_message
from app.agent.deepseek_agent import generate_report as ds_generate_report, chat_with_context, get_agent_step

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)


@api_bp.route("/counters/<counter_id>/goals")
def get_goals(counter_id):
    """Get goals for a Metrika counter."""
    token = _get_token()
    if not token:
        return jsonify([])
    try:
        resp = http_requests.get(
            f"https://api-metrika.yandex.net/management/v1/counter/{counter_id}/goals",
            headers={"Authorization": f"OAuth {token}"},
        )
        goals_data = resp.json().get("goals", [])
        goals = [{"id": str(g["id"]), "name": g["name"], "type": g.get("type", "unknown")} for g in goals_data]
        # Add ecommerce revenue as option
        goals.insert(0, {"id": "ecommerce_revenue", "name": "Доход от интернет-торговли", "type": "ecommerce"})
        return jsonify(goals)
    except Exception as e:
        return jsonify([{"id": "ecommerce_revenue", "name": "Доход от интернет-торговли", "type": "ecommerce"}])


@api_bp.route("/projects", methods=["POST"])
def create_project():
    """Create project and start async report generation."""
    data = request.json or {}
    counter_id = data.get("counter_id") or session.get("setup_counter_id")
    goal_id = data.get("goal_id") or session.get("setup_goal_id")
    objective = data.get("objective") or session.get("setup_objective", "sales")

    comment = data.get("comment") or session.get("setup_comment", "")

    # Get site name from Metrika
    site_name = f"Сайт #{counter_id}"
    goal_name = ""
    host_id = None
    token = _get_token() or ""
    if token:
        try:
            resp = http_requests.get(
                f"https://api-metrika.yandex.net/management/v1/counters",
                headers={"Authorization": f"OAuth {token}"},
            )
            for c in resp.json().get("counters", []):
                if str(c["id"]) == str(counter_id):
                    site_name = c["site"]
                    break
        except Exception:
            pass
        # Get goal name
        if goal_id and goal_id != "ecommerce_revenue":
            try:
                resp = http_requests.get(
                    f"https://api-metrika.yandex.net/management/v1/counter/{counter_id}/goals",
                    headers={"Authorization": f"OAuth {token}"},
                )
                for g in resp.json().get("goals", []):
                    if str(g["id"]) == str(goal_id):
                        goal_name = g["name"]
                        break
            except Exception:
                pass
        elif goal_id == "ecommerce_revenue":
            goal_name = "Доход от интернет-торговли"
        # Find Webmaster host_id
        try:
            from app.integrations.webmaster import find_host_id
            _, host_id = find_host_id(token, site_name)
        except Exception:
            pass

    # Get or create user
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    project = Project(
        site_name=site_name,
        objective=objective,
        metrika_counter_id=counter_id,
        metrika_goal_id=goal_id,
        metrika_goal_name=goal_name,
        webmaster_host_id=host_id,
        user_id=user_id,
        comment=comment,
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
    """Background task: collect data + send to agent API (async)."""
    from app import create_app
    app = create_app()
    with app.app_context():
        from app.models import Project
        project = Project.query.get(project_id)
        host_id = project.webmaster_host_id if project else None
        data = {}
        try:
            with logged_request("metrika", "collect_all", project_id=project_id) as log:
                data = collect_data(token, counter_id, goal_id=goal_id, host_id=host_id)
                log.ok(request_url=f"metrika:{counter_id}", response_snippet="OK")
        except Exception as e:
            from app.services.logger import log_integration
            log_integration("metrika", "collect_all", level="error", project_id=project_id, error_message=str(e))
            # Partial collection fallback
            try:
                from app.integrations.metrika import (
                    report_entry_pages, report_popular_pages, report_sources, report_day_hour,
                    report_cities, report_ecommerce_funnel, report_devices, report_demographics,
                    report_keywords
                )
                metrika = {}
                for name, fn in [
                    ("entry_pages", lambda: report_entry_pages(token, counter_id, goal_id)),
                    ("popular_pages", lambda: report_popular_pages(token, counter_id, goal_id)),
                    ("sources", lambda: report_sources(token, counter_id, goal_id)),
                    ("keywords", lambda: report_keywords(token, counter_id, goal_id)),
                    ("day_hour", lambda: report_day_hour(token, counter_id, goal_id)),
                    ("cities", lambda: report_cities(token, counter_id, goal_id)),
                    ("devices", lambda: report_devices(token, counter_id, goal_id)),
                    ("demographics", lambda: report_demographics(token, counter_id, goal_id)),
                    ("ecommerce_funnel", lambda: report_ecommerce_funnel(token, counter_id)),
                ]:
                    try:
                        metrika[name] = fn()
                    except Exception:
                        pass
                data = {"metrika": metrika, "webmaster": {}}
            except Exception:
                pass
            try:
                from app.integrations.webmaster import collect_all_webmaster
                if host_id:
                    data["webmaster"] = collect_all_webmaster(token, host_id)
            except Exception:
                pass

        # Save raw_data
        report = db.session.get(Report, report_id)
        report.raw_data = json.dumps(data, ensure_ascii=False) if data else None
        db.session.commit()

        # Build reports array for agent API
        reports = []
        metrika_data = data.get("metrika", {})
        webmaster_data = data.get("webmaster", {})
        for rtype in ["traffic", "sources", "search_phrases", "landing_pages", "geo", "devices", "goals"]:
            if rtype in metrika_data:
                reports.append({"source": "metrika", "type": rtype, "data": metrika_data[rtype]})
        for rtype in ["indexing", "search_queries"]:
            if rtype in webmaster_data:
                reports.append({"source": "webmaster", "type": rtype, "data": webmaster_data[rtype]})

        # Build yandex config
        yandex = None
        if token:
            yandex = {"token": token}
            if counter_id:
                yandex["metrika_counter_id"] = int(counter_id)
            if host_id:
                yandex["webmaster_host_id"] = host_id

        goal_text = _build_goal_text(project)

        # Send to agent
        try:
            with logged_request("agent", "send_init", project_id=project_id) as log:
                result = send_project_init(
                    project_id=project_id,
                    site_name=project.site_name if project else "unknown",
                    reports=reports,
                    goal=goal_text,
                    yandex=yandex,
                )
                log.ok(response_snippet=f"job_id={result.get('job_id')}")
        except Exception as e:
            from app.services.logger import log_integration
            log_integration("agent", "send_init", level="error", project_id=project_id, error_message=str(e))
            report = db.session.get(Report, report_id)
            report.ai_report_text = f"Ошибка отправки данных агенту: {str(e)}"
            db.session.commit()


@api_bp.route("/projects/<int:project_id>", methods=["DELETE"])
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    # Delete related records
    Report.query.filter_by(project_id=project_id).delete()
    IntegrationLog.query.filter_by(project_id=project_id).delete()
    ChatMessage.query.filter_by(project_id=project_id).delete()
    db.session.delete(project)
    db.session.commit()
    return jsonify({"status": "ok"})


@api_bp.route("/projects/<int:project_id>/chart-data")
def chart_data(project_id):
    """Return chart-ready data from stored report."""
    report = Report.query.filter_by(project_id=project_id).order_by(Report.id.desc()).first()
    if not report or not report.raw_data:
        return jsonify({})

    data = json.loads(report.raw_data)
    metrika = data.get("metrika", {})
    result = {}

    # 1. Traffic by day of week (sorted Mon-Sun)
    day_hour = metrika.get("day_hour", {})
    by_day = day_hour.get("by_day", {})
    if by_day and by_day.get("rows"):
        day_order = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        rows_map = {r["dimensions"][0]: r["metrics"][0] for r in by_day["rows"]}
        result["traffic_by_day"] = {
            "labels": day_order,
            "values": [rows_map.get(d, 0) for d in day_order],
        }

    # 2. Traffic by hour (sorted 0-23)
    by_hour = day_hour.get("by_hour", {})
    if by_hour and by_hour.get("rows"):
        rows_map = {r["dimensions"][0]: r["metrics"][0] for r in by_hour["rows"]}
        result["traffic_by_hour"] = {
            "labels": [f"{h}:00" for h in range(24)],
            "values": [rows_map.get(f"{h}:00", 0) for h in range(24)],
        }

    # 3. Sources
    src_report = metrika.get("sources", {})
    if src_report and src_report.get("rows"):
        result["sources"] = {
            "labels": [r["dimensions"][0] for r in src_report["rows"][:8]],
            "values": [r["metrics"][0] for r in src_report["rows"][:8]],
        }

    # 4. Entry pages
    entry = metrika.get("entry_pages", {})
    if entry and entry.get("rows"):
        merged = {}
        for r in entry["rows"]:
            url = r["dimensions"][0]
            # Normalize: remove protocol and trailing slash
            key = url.replace("https://", "").replace("http://", "").rstrip("/")
            merged[key] = merged.get(key, 0) + r["metrics"][0]
        sorted_pages = sorted(merged.items(), key=lambda x: -x[1])[:10]
        result["entry_pages"] = {
            "labels": [p[0] for p in sorted_pages],
            "values": [p[1] for p in sorted_pages],
        }

    # 5. Cities
    cities = metrika.get("cities", {})
    if cities and cities.get("rows"):
        result["cities"] = {
            "labels": [r["dimensions"][0] for r in cities["rows"][:10]],
            "values": [r["metrics"][0] for r in cities["rows"][:10]],
        }

    # 5.5 Popular pages
    popular = metrika.get("popular_pages", {})
    if popular and popular.get("rows"):
        merged = {}
        for r in popular["rows"]:
            url = r["dimensions"][0]
            key = url.replace("https://", "").replace("http://", "").rstrip("/")
            merged[key] = merged.get(key, 0) + r["metrics"][0]
        sorted_pages = sorted(merged.items(), key=lambda x: -x[1])[:10]
        result["popular_pages"] = {
            "labels": [p[0] for p in sorted_pages],
            "values": [p[1] for p in sorted_pages],
        }

    # 6. Keywords
    kw = metrika.get("keywords", {})
    if kw and kw.get("rows"):
        result["keywords"] = {
            "labels": [r["dimensions"][0] for r in kw["rows"][:15]],
            "values": [r["metrics"][0] for r in kw["rows"][:15]],
        }

    # 7. Ecommerce funnel
    funnel = metrika.get("ecommerce_funnel", [])
    if funnel and isinstance(funnel, list):
        result["funnel"] = {
            "labels": [s["step"] for s in funnel],
            "values": [s["value"] for s in funnel],
        }

    # 8. Devices
    devices = metrika.get("devices", {})
    if devices and devices.get("rows"):
        result["devices"] = {
            "labels": [r["dimensions"][0] for r in devices["rows"]],
            "values": [r["metrics"][0] for r in devices["rows"]],
        }

    # 9. Demographics
    demo = metrika.get("demographics", {})
    by_sex = demo.get("by_sex", {})
    by_age = demo.get("by_age", {})
    if (by_sex and by_sex.get("rows")) or (by_age and by_age.get("rows")):
        demo_labels = []
        demo_values = []
        if by_sex and by_sex.get("rows"):
            for r in by_sex["rows"]:
                demo_labels.append(r["dimensions"][0])
                demo_values.append(r["metrics"][0])
        if by_age and by_age.get("rows"):
            for r in by_age["rows"]:
                demo_labels.append(r["dimensions"][0])
                demo_values.append(r["metrics"][0])
        result["demographics"] = {"labels": demo_labels, "values": demo_values}

    return jsonify(result)


@api_bp.route("/projects/<int:project_id>/raw-data")
def raw_data(project_id):
    """Return raw data sent to agent."""
    report = Report.query.filter_by(project_id=project_id).order_by(Report.id.desc()).first()
    if not report or not report.raw_data:
        return jsonify({})
    data = json.loads(report.raw_data)

    # Normalize URLs: merge http/https duplicates
    def normalize_rows(rows):
        if not rows:
            return rows
        merged = {}
        order = []
        for r in rows:
            key = r["dimensions"][0]
            if key.startswith("http://") or key.startswith("https://"):
                norm = key.replace("https://", "").replace("http://", "").rstrip("/")
            else:
                norm = key
            if norm in merged:
                # Sum metrics
                merged[norm] = {
                    "dimensions": [norm],
                    "metrics": [a + b for a, b in zip(merged[norm]["metrics"], r["metrics"])]
                }
            else:
                merged[norm] = {"dimensions": [norm], "metrics": list(r["metrics"])}
                order.append(norm)
        return [merged[k] for k in order]

    metrika = data.get("metrika", {})
    for key in ["entry_pages", "sources", "keywords", "cities"]:
        section = metrika.get(key)
        if section and isinstance(section, dict) and section.get("rows"):
            section["rows"] = normalize_rows(section["rows"])

    return data


@api_bp.route("/agent/callback", methods=["POST"])
def agent_callback():
    """Disabled — DeepSeek agent is primary."""
    return jsonify({"ok": True, "note": "Keng callback disabled"})


@api_bp.route("/projects/<int:project_id>/chat", methods=["POST"])
def chat(project_id):
    """Send message to AI agent and return response."""
    data = request.json
    message = data.get("message", "")
    if not message.strip():
        return jsonify({"error": "Empty message"}), 400

    project = Project.query.get_or_404(project_id)

    # Save user message
    user_msg = ChatMessage(project_id=project_id, role="user", text=message)
    db.session.add(user_msg)
    db.session.commit()

    # Try DeepSeek directly, fallback to external agent
    report = Report.query.filter_by(project_id=project_id).order_by(Report.id.desc()).first()
    raw_data = json.loads(report.raw_data) if report and report.raw_data else None

    try:
        response_text = chat_with_context(project_id, message, data=raw_data, report_text=report.ai_report_text if report else None)
        assistant_msg = ChatMessage(project_id=project_id, role="assistant", text=response_text)
        db.session.add(assistant_msg)
        db.session.commit()
        return jsonify({"status": "ok", "response": response_text})
    except Exception as e:
        logger.error(f"DeepSeek chat failed, fallback to external: {e}")
        try:
            send_chat_message(project_id, message)
            return jsonify({"status": "ok", "message": "Вопрос отправлен агенту. Ответ появится в чате."})
        except Exception as e2:
            return jsonify({"error": str(e2)}), 500


@api_bp.route("projects/<int:project_id>/chat-history")
def chat_history(project_id):
    messages = ChatMessage.query.filter_by(project_id=project_id).order_by(ChatMessage.id.asc()).all()
    return jsonify({"messages": [{"role": m.role, "text": m.text} for m in messages]})


@api_bp.route("projects/<int:project_id>/chat-clear", methods=["POST"])
def chat_clear(project_id):
    msgs = ChatMessage.query.filter_by(project_id=project_id).order_by(ChatMessage.id).all()
    if msgs:
        from app.models import ChatArchive
        archive = ChatArchive(
            project_id=project_id,
            messages=json.dumps([{"role": m.role, "text": m.text, "created": m.created_at.isoformat() if m.created_at else None} for m in msgs], ensure_ascii=False)
        )
        db.session.add(archive)
        ChatMessage.query.filter_by(project_id=project_id).delete()
        db.session.commit()
    return jsonify({"status": "ok"})


@api_bp.route("projects/<int:project_id>/agent-step")
def agent_step(project_id):
    step = get_agent_step(project_id)
    return jsonify(step)


@api_bp.route("/projects/<int:project_id>/retry", methods=["POST"])
def retry_report(project_id):
    """Retry sending project data to agent."""
    report = Report.query.filter_by(project_id=project_id).order_by(Report.id.desc()).first()
    project = Project.query.get_or_404(project_id)
    if not report or not report.raw_data:
        return jsonify({"error": "No data to retry"}), 400

    data = json.loads(report.raw_data)
    metrika_data = data.get("metrika", {})
    webmaster_data = data.get("webmaster", {})
    reports = []
    for rtype in ["traffic", "sources", "search_phrases", "landing_pages", "geo", "devices", "goals"]:
        if rtype in metrika_data:
            reports.append({"source": "metrika", "type": rtype, "data": metrika_data[rtype]})
    for rtype in ["indexing", "search_queries"]:
        if rtype in webmaster_data:
            reports.append({"source": "webmaster", "type": rtype, "data": webmaster_data[rtype]})

    yandex = None
    token = project.user.oauth_token if project.user else None
    if token:
        yandex = {"token": token}
        if project.metrika_counter_id:
            yandex["metrika_counter_id"] = int(project.metrika_counter_id)
        if project.webmaster_host_id:
            yandex["webmaster_host_id"] = project.webmaster_host_id

    goal_text = _build_goal_text(project)

    # Clear old report
    report.ai_report_text = ""
    db.session.commit()

    # External agent only
    try:
        send_project_init(
            project_id=project_id,
            site_name=project.site_name,
            reports=reports,
            goal=goal_text,
            yandex=yandex,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ok"})


@api_bp.route("/projects/<int:project_id>/deepseek-report", methods=["POST"])
def deepseek_report(project_id):
    """Generate report via DeepSeek agent only."""
    report = Report.query.filter_by(project_id=project_id).order_by(Report.id.desc()).first()
    project = Project.query.get_or_404(project_id)
    if not report or not report.raw_data:
        return jsonify({"error": "No data to retry"}), 400

    data = json.loads(report.raw_data)
    goal_text = _build_goal_text(project)

    report.ai_report_text = ""
    db.session.commit()

    _objective = project.objective
    _project_id = project_id
    _token = project.user.oauth_token if project.user else None
    _counter_id = int(project.metrika_counter_id) if project.metrika_counter_id else None
    _goal_id = project.metrika_goal_id if hasattr(project, 'metrika_goal_id') and project.metrika_goal_id else None
    _wm_host_id = project.webmaster_host_id if hasattr(project, 'webmaster_host_id') and project.webmaster_host_id else None

    def _run():
        from app import create_app
        app = create_app()
        with app.app_context():
            try:
                text = ds_generate_report(
                    data, objective=_objective, goal=goal_text,
                    token=_token, counter_id=_counter_id, goal_id=_goal_id,
                    webmaster_host_id=_wm_host_id, project_id=_project_id,
                )
                report_obj = Report.query.filter_by(project_id=_project_id).order_by(Report.id.desc()).first()
                report_obj.ai_report_text = text
                db.session.commit()
                logger.info(f"DeepSeek report saved for project {_project_id}")
            except Exception as e:
                logger.error(f"DeepSeek failed: {e}")
                report_obj = Report.query.filter_by(project_id=_project_id).order_by(Report.id.desc()).first()
                report_obj.ai_report_text = f"Ошибка: {str(e)}"
                db.session.commit()

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "ok"})


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
        "validation_score": report.validation_score or 0,
        "validation_issues": json.loads(report.validation_issues) if report.validation_issues else [],
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


@api_bp.route("/feedback", methods=["POST"])
def submit_feedback():
    data = request.json or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"ok": False, "error": "Сообщение обязательно"}), 400
    from app.models import Feedback
    fb = Feedback(name=name or None, email=email or None, message=message)
    db.session.add(fb)
    db.session.commit()
    return jsonify({"ok": True})
