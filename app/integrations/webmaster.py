"""
Yandex Webmaster API client for Razgon.

API docs: https://yandex.ru/dev/webmaster/doc/dg/reference/host-id.html
All endpoints require OAuth token + host_id (user's site in Webmaster).

Base URL: https://api.webmaster.yandex.net/v4/user/{uid}/hosts/{host_id}/...
"""
import requests

WEBMASTER_BASE = "https://api.webmaster.yandex.net/v4"


def _headers(token):
    return {"Authorization": f"OAuth {token}"}


def _get_uid(token):
    """Get user UID from Webmaster API."""
    resp = requests.get(f"{WEBMASTER_BASE}/user", headers=_headers(token))
    resp.raise_for_status()
    return resp.json()["user_id"]


def _host_base(token, host_id):
    """Build base URL for host endpoints."""
    uid = _get_uid(token)
    return f"{WEBMASTER_BASE}/user/{uid}/hosts/{host_id}"


# ==========================================
# Report 1: Top search queries
# ==========================================
def report_search_queries(token, host_id, limit=30):
    """
    Топ поисковых запросов: показы, клики, средняя позиция.
    Для всех целей — показывает по каким запросам находят сайт.
    """
    # Stub
    return {
        "queries": [
            {"query": "купить телефон москва", "impressions": 3200, "clicks": 180, "position": 3.2, "ctr": 5.6},
            {"query": "смартфон недорого", "impressions": 2100, "clicks": 95, "position": 4.8, "ctr": 4.5},
            {"query": "iphone 15 цена", "impressions": 1800, "clicks": 210, "position": 2.1, "ctr": 11.7},
            {"query": "телефон самсунг", "impressions": 1500, "clicks": 60, "position": 6.3, "ctr": 4.0},
            {"query": "xiaomi redmi note", "impressions": 1200, "clicks": 85, "position": 3.5, "ctr": 7.1},
        ]
    }
    # Real API call:
    # base = _host_base(token, host_id)
    # resp = requests.get(f"{base}/search-queries/query-list", headers=_headers(token),
    #     params={"order_by": "TOTAL_SHOWS:DESC", "limit": limit})
    # resp.raise_for_status()
    # return {"queries": resp.json().get("queries", [])}


# ==========================================
# Report 2: High impressions / low CTR queries
# ==========================================
def report_low_ctr_queries(token, host_id, min_impressions=100, limit=20):
    """
    Запросы с высокими показами и низким CTR — упущенный потенциал.
    Для целей: увеличить охват, сэкономить на рекламе.
    """
    # Stub
    return {
        "queries": [
            {"query": "купить телефон", "impressions": 5400, "clicks": 45, "position": 8.2, "ctr": 0.8},
            {"query": "смартфон отзывы", "impressions": 2800, "clicks": 30, "position": 7.5, "ctr": 1.1},
            {"query": "лучший телефон 2025", "impressions": 1900, "clicks": 22, "position": 9.1, "ctr": 1.2},
        ]
    }
    # Real: filter search-queries by TOTAL_SHOWS > min_impressions, sort by CTR ASC


# ==========================================
# Report 3: Crawl errors
# ==========================================
def report_crawl_errors(token, host_id):
    """
    Ошибки сканирования: 404, 5xx, битые изображения и т.д.
    Для цели: поднять эффективность сайта.
    """
    # Stub
    return {
        "summary": {
            "fatal": 3,
            "critical": 8,
            "warning": 15,
            "informational": 42,
        },
        "top_errors": [
            {"code": "404", "count": 12, "sample_urls": ["/old-page", "/removed-product", "/blog/old-post"]},
            {"code": "500", "count": 2, "sample_urls": ["/api/catalog"]},
            {"code": "broken_images", "count": 5, "sample_urls": ["/product/123"]},
        ]
    }
    # Real API call:
    # base = _host_base(token, host_id)
    # resp = requests.get(f"{base}/diagnostics", headers=_headers(token))
    # resp.raise_for_status()
    # return resp.json()


# ==========================================
# Report 4: Excluded pages
# ==========================================
def report_excluded_pages(token, host_id, limit=20):
    """
    Исключённые страницы — что не попало в индекс и почему.
    Для цели: поднять эффективность сайта.
    """
    # Stub
    return {
        "total_excluded": 30,
        "reasons": [
            {"reason": "Страница не найдена (404)", "count": 12},
            {"reason": "Дубликат", "count": 8},
            {"reason": "Редирект", "count": 5},
            {"reason": "Заблокировано в robots.txt", "count": 3},
            {"reason": "Canonical указывает на другую страницу", "count": 2},
        ],
        "sample_urls": [
            {"url": "/old-catalog", "reason": "Страница не найдена (404)"},
            {"url": "/page?ref=affiliate", "reason": "Дубликат"},
            {"url": "/admin/login", "reason": "Заблокировано в robots.txt"},
        ]
    }
    # Real: /index-history or /diagnostics


# ==========================================
# Report 5: Indexing status
# ==========================================
def report_indexing_status(token, host_id):
    """
    Статус индексации: сколько страниц в индексе vs исключено.
    Общий показатель здоровья сайта.
    """
    # Stub
    return {
        "indexed": 245,
        "excluded": 30,
        "waiting": 5,
        "total_known": 280,
        "index_ratio": round(245 / 280 * 100, 1),
    }
    # Real:
    # base = _host_base(token, host_id)
    # resp = requests.get(f"{base}/summary", headers=_headers(token))
    # resp.raise_for_status()


# ==========================================
# Report 6: Popular pages from search
# ==========================================
def report_popular_search_pages(token, host_id, limit=15):
    """
    Популярные страницы из поискового трафика.
    Какие страницы приносят больше всего визитов из поиска.
    """
    # Stub
    return {
        "pages": [
            {"url": "/", "clicks": 450, "impressions": 2100, "position": 2.8},
            {"url": "/catalog", "clicks": 320, "impressions": 1800, "position": 3.5},
            {"url": "/product/iphone-15", "clicks": 210, "impressions": 900, "position": 1.8},
            {"url": "/blog/best-phones", "clicks": 150, "impressions": 650, "position": 4.2},
            {"url": "/contacts", "clicks": 30, "impressions": 400, "position": 8.5},
        ]
    }
    # Real: search-queries grouped by page URL


# ==========================================
# Collect all Webmaster reports
# ==========================================
def collect_all_webmaster(token, host_id):
    """Collect all 6 Webmaster reports at once."""
    return {
        "search_queries": report_search_queries(token, host_id),
        "low_ctr_queries": report_low_ctr_queries(token, host_id),
        "crawl_errors": report_crawl_errors(token, host_id),
        "excluded_pages": report_excluded_pages(token, host_id),
        "indexing": report_indexing_status(token, host_id),
        "popular_search_pages": report_popular_search_pages(token, host_id),
    }
