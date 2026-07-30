from flask import Blueprint, render_template, session
from app.models import Project
from app import db

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def promo():
    return render_template("promo_v4.html")


@main_bp.route("/v2")
def promo_v2():
    return render_template("promo_v2.html")


@main_bp.route("/v5")
def promo_v5():
    return render_template("promo_v5.html")


@main_bp.route("/v6")
def promo_v6():
    return render_template("promo_v6.html")


@main_bp.route("/v7")
def promo_v7():
    return render_template("promo_v7.html")


@main_bp.route("/v8")
def promo_v8():
    return render_template("promo_v8.html")


@main_bp.route("/v9")
def promo_v9():
    return render_template("promo_v9.html")


@main_bp.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    if user_id:
        projects = Project.query.filter_by(user_id=user_id).order_by(Project.id.desc()).all()
    else:
        projects = []
    return render_template("dashboard.html", projects=projects)


@main_bp.route("/feedback")
def feedback():
    return render_template("feedback.html")
