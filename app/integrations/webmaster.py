"""
Yandex Webmaster API client for Razgon.

API docs: https://yandex.ru/dev/webmaster/doc/dg/reference/host-id.html
"""
import requests

WEBMASTER_BASE = "https://api.webmaster.yandex.net/v4"


def _headers(token):
    return {"Authorization": f"OAuth {token}"}


def get_uid(token):
    """Get user UID from Webmaster API."""
    resp = requests.get(f"{WEBMASTER_BASE}/user", headers=_headers(token))
    resp.raise_for_status()
    return resp.json()["user_id"]


def find_host_id(token, site_url):
    """
    Find host_id in Webmaster by matching site URL.
    Returns (host_id, main_mirror_host_id) or (None, None).
    Tries to match by domain against unicode/ascii host URLs.
    """
    uid = get_uid(token)
    resp = requests.get(f"{WEBMASTER_BASE}/user/{uid}/hosts", headers=_headers(token))
    resp.raise_for_status()
    hosts = resp.json().get("hosts", [])

    # Normalize target domain
    target = site_url.replace("https://", "").replace("http://", "").rstrip("/").lower()
    # Handle punycode
    if "xn--" not in target:
        try:
            import idna
            target_punycode = idna.encode(target).decode()
        except Exception:
            target_punycode = target
    else:
        target_punycode = target

    for h in hosts:
        for url_field in ["unicode_host_url", "ascii_host_url"]:
            host_url = h.get(url_field, "").replace("https://", "").replace("http://", "").rstrip("/").lower()
            if host_url == target or host_url == target_punycode:
                # Prefer main mirror
                mirror = h.get("main_mirror", {})
                if mirror:
                    return h["host_id"], mirror.get("host_id", h["host_id"])
                return h["host_id"], h["host_id"]

    return None, None


def _host_base(token, host_id):
    uid = get_uid(token)
    return f"{WEBMASTER_BASE}/user/{uid}/hosts/{host_id}"


# ==========================================
# Report 1: Search queries (popular)
# ==========================================
def report_search_queries(token, host_id, limit=50):
    """
    Популярные поисковые запросы из Вебмастера.
    Возвращает текст запросов, отсортированных по показам.
    """
    uid = get_uid(token)
    url = f"{WEBMASTER_BASE}/user/{uid}/hosts/{host_id}/search-queries/popular"
    resp = requests.get(url, headers=_headers(token),
        params={"order_by": "TOTAL_SHOWS", "limit": limit})
    resp.raise_for_status()
    data = resp.json()
    queries = []
    for q in data.get("queries", []):
        entry = {
            "query": q.get("query_text", ""),
            "query_id": q.get("query_id", ""),
        }
        # Include indicators if available
        indicators = q.get("indicators", {})
        if indicators:
            entry.update({
                "shows": indicators.get("TOTAL_SHOWS", 0),
                "clicks": indicators.get("TOTAL_CLICKS", 0),
                "position": indicators.get("AVG_SHOW_POSITION", 0),
                "click_position": indicators.get("AVG_CLICK_POSITION", 0),
            })
        queries.append(entry)
    return {"queries": queries, "date_from": data.get("date_from"), "date_to": data.get("date_to")}


# ==========================================
# Report 2: Site summary
# ==========================================
def report_summary(token, host_id):
    """
    Общая сводка: SQI, страниц в индексе, исключённых, проблемы.
    """
    uid = get_uid(token)
    url = f"{WEBMASTER_BASE}/user/{uid}/hosts/{host_id}/summary"
    resp = requests.get(url, headers=_headers(token))
    resp.raise_for_status()
    data = resp.json()
    return {
        "sqi": data.get("sqi", 0),
        "indexed": data.get("searchable_pages_count", 0),
        "excluded": data.get("excluded_pages_count", 0),
        "problems": data.get("site_problems", {}),
    }


# ==========================================
# Report 3: Diagnostics
# ==========================================
def report_diagnostics(token, host_id):
    """
    Диагностика сайта: проблемы и рекомендации от Яндекса.
    """
    uid = get_uid(token)
    url = f"{WEBMASTER_BASE}/user/{uid}/hosts/{host_id}/diagnostics"
    resp = requests.get(url, headers=_headers(token))
    resp.raise_for_status()
    data = resp.json()
    problems = []
    for key, val in data.get("problems", {}).items():
        if val.get("state") != "ABSENT":
            problems.append({
                "code": key,
                "severity": val.get("severity", ""),
                "state": val.get("state", ""),
            })
    return {"problems": problems, "total": len(problems)}


# ==========================================
# Collect all
# ==========================================
def collect_all_webmaster(token, host_id):
    """Collect available Webmaster reports."""
    result = {}
    if not host_id:
        return result

    try:
        result["summary"] = report_summary(token, host_id)
    except Exception:
        pass

    try:
        result["search_queries"] = report_search_queries(token, host_id)
    except Exception:
        pass

    try:
        result["diagnostics"] = report_diagnostics(token, host_id)
    except Exception:
        pass

    return result
