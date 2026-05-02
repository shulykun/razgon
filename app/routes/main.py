from flask import Blueprint, render_template, session
from app.models import Project
from app import db

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def promo():
    return render_template("promo_v3.html")


@main_bp.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    if user_id:
        projects = Project.query.filter_by(user_id=user_id).order_by(Project.id.desc()).all()
    else:
        projects = []
    return render_template("dashboard.html", projects=projects)
