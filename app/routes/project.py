from flask import Blueprint, render_template

project_bp = Blueprint("project", __name__)


@project_bp.route("/<int:project_id>/report")
def report(project_id):
    # TODO: load project + report from DB
    return render_template("report.html", project_id=project_id)
