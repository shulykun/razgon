import json
import threading
import requests as http_requests
from flask import Blueprint, request, jsonify, session
from app import db
from app.models import Project, Report, IntegrationLog, ChatMessage
from app.services.report import collect_data, generate_report
from app.services.logger import logged_request

api_bp = Blueprint("api", __name__)


@api_bp.route("/counters/<counter_id>/goals")
def get_goals(counter_id):
    """Get goals for a Metrika counter."""
    token = session.get("oauth_token")
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

    # Get site name from Metrika
    site_name = f"Сайт #{counter_id}"
    goal_name = ""
    host_id = None
    token = session.get("oauth_token", "")
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
            # Try partial collection — collect reports one by one
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
            # Try webmaster separately
            try:
                from app.integrations.webmaster import collect_all_webmaster
                if host_id:
                    data["webmaster"] = collect_all_webmaster(token, host_id)
            except Exception:
                pass

        # Always save raw_data
        report = db.session.get(Report, report_id)
        report.raw_data = json.dumps(data, ensure_ascii=False) if data else None
        db.session.commit()

        try:
            with logged_request("agent", "generate_report", project_id=project_id) as log:
                ai_text = generate_report(data, objective=objective)
                log.ok(response_snippet=ai_text[:500] if ai_text else None)
        except Exception as e:
            ai_text = f"Ошибка генерации отчёта: {str(e)}"

        report = db.session.get(Report, report_id)
        report.ai_report_text = ai_text
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
