from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def promo():
    return render_template("promo.html")


@main_bp.route("/dashboard")
def dashboard():
    # TODO: get user projects from DB
    projects = []
    return render_template("dashboard.html", projects=projects)
