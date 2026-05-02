import requests
from flask import Blueprint, render_template, session, current_app, redirect, url_for, jsonify, request

setup_bp = Blueprint("setup", __name__)


def get_metrika_counters(token):
    resp = requests.get(
        "https://api-metrika.yandex.net/management/v1/counters",
        headers={"Authorization": f"OAuth {token}"},
    )
    counters = resp.json().get("counters", [])
    return [{"id": str(c["id"]), "name": c["name"], "site": c["site"]} for c in counters]


def _require_auth():
    if not session.get("oauth_token"):
        return redirect(url_for("auth.login"))
    return None


# --- Step 1: Site (счётчик) ---
@setup_bp.route("/site")
def step_site():
    redir = _require_auth()
    if redir:
        return redir
    token = session.get("oauth_token")
    counters = get_metrika_counters(token)
    return render_template("step_site.html", step=1, counters=counters)


# --- Step 2: Goal on counter (цель на счётчике) ---
@setup_bp.route("/goal")
def step_goal():
    redir = _require_auth()
    if redir:
        return redir
    if not session.get("setup_counter_id"):
        return redirect(url_for("setup.step_site"))
    return render_template("step_goal.html", step=2)


# --- Step 3: Objective (цель запуска) ---
@setup_bp.route("/objective")
def step_objective():
    redir = _require_auth()
    if redir:
        return redir
    if not session.get("setup_counter_id"):
        return redirect(url_for("setup.step_site"))
    return render_template("step_objective.html", step=3)


# --- API: save state between steps ---
@setup_bp.route("/api/counter", methods=["POST"])
def api_set_counter():
    data = request.get_json()
    session["setup_counter_id"] = data.get("counter_id")
    return jsonify(ok=True)


@setup_bp.route("/api/goal", methods=["POST"])
def api_set_goal():
    data = request.get_json()
    session["setup_goal_id"] = data.get("goal_id")
    return jsonify(ok=True)


@setup_bp.route("/api/objective", methods=["POST"])
def api_set_objective():
    data = request.get_json()
    session["setup_objective"] = data.get("objective", "sales")
    return jsonify(ok=True)


@setup_bp.route("/api/state")
def api_get_state():
    return jsonify({
        "objective": session.get("setup_objective"),
        "counter_id": session.get("setup_counter_id"),
        "goal_id": session.get("setup_goal_id"),
    })


# Legacy redirect
@setup_bp.route("/choose-site")
def choose_site():
    return redirect(url_for("setup.step_site"))
