import requests
from flask import Blueprint, render_template, session, current_app, redirect, url_for

setup_bp = Blueprint("setup", __name__)


def get_metrika_counters(token):
    """Get list of Metrika counters (sites) for the user."""
    # Stub: return placeholder data
    if current_app.config["YANDEX_CLIENT_ID"] == "placeholder":
        return [
            {"id": "12345", "name": "example.com", "site": "https://example.com"},
            {"id": "67890", "name": "my-shop.ru", "site": "https://my-shop.ru"},
        ]
    resp = requests.get(
        "https://api-metrika.yandex.net/management/v1/counters",
        headers={"Authorization": f"OAuth {token}"},
    )
    counters = resp.json().get("counters", [])
    return [{"id": str(c["id"]), "name": c["name"], "site": c["site"]} for c in counters]


@setup_bp.route("/choose-site")
def choose_site():
    token = session.get("oauth_token")
    if not token:
        return redirect(url_for("auth.login"))
    counters = get_metrika_counters(token)
    return render_template("setup.html", counters=counters)
