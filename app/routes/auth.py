import requests
from flask import Blueprint, redirect, url_for, session, request, render_template, current_app

auth_bp = Blueprint("auth", __name__)

YANDEX_AUTH_URL = "https://oauth.yandex.ru/authorize"
YANDEX_TOKEN_URL = "https://oauth.yandex.ru/token"


@auth_bp.route("/login")
def login():
    client_id = current_app.config["YANDEX_CLIENT_ID"]
    redirect_uri = current_app.config["YANDEX_REDIRECT_URI"]
    scope = "metrica:read webmaster:read"
    url = (
        f"{YANDEX_AUTH_URL}?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scope}"
    )
    return redirect(url)


@auth_bp.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Authorization failed", 400

    # Exchange code for token
    resp = requests.post(
        YANDEX_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": current_app.config["YANDEX_CLIENT_ID"],
            "client_secret": current_app.config["YANDEX_CLIENT_SECRET"],
            "redirect_uri": current_app.config["YANDEX_REDIRECT_URI"],
        },
    )
    token_data = resp.json()
    access_token = token_data.get("access_token")

    if not access_token:
        return "Token exchange failed", 400

    # Get user info
    user_info = requests.get(
        "https://login.yandex.ru/info",
        headers={"Authorization": f"OAuth {access_token}"},
    ).json()

    session["oauth_token"] = access_token
    session["yandex_id"] = str(user_info.get("id"))
    session["user_name"] = user_info.get("real_name", user_info.get("login", "User"))

    # TODO: create/update User in DB

    return redirect(url_for("setup.choose_site"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.promo"))
