from flask import Blueprint, render_template
from datetime import datetime, timedelta
from app.models import Project

project_bp = Blueprint("project", __name__)

OBJECTIVE_LABELS = {
    "sales": "Увеличить охват и продажи",
    "optimize": "Сэкономить на рекламе",
    "efficiency": "Поднять эффективность сайта",
    "audience": "Понять портрет клиента",
}


@project_bp.route("/<int:project_id>/report")
def report(project_id):
    project = Project.query.get_or_404(project_id)
    end = datetime.now()
    start = end - timedelta(days=30)

    goal_name = project.metrika_goal_name or "—"
    objective_label = OBJECTIVE_LABELS.get(project.objective, project.objective or "—")

    return render_template("report.html",
        project_id=project_id,
        project=project,
        start_date=start.strftime("%d.%m.%Y"),
        end_date=end.strftime("%d.%m.%Y"),
        goal_name=goal_name,
        objective_label=objective_label,
    )
