"""
Yandex Metrika API client for Razgon.

API docs: https://yandex.ru/dev/metrika/doc/api2/stat/intro.html
Reports use stat/v1/data with dimensions & metrics.

Common metrics:
- ym:s:visits — сессии
- ym:s:users — пользователи
- ym:s:bounceRate — отказы %
- ym:s:pageDepth — глубина просмотра
- ym:s:avgVisitDurationSeconds — средняя длительность
- ym:s:goal<id>reaches — достижения цели
- ym:s:goal<id>conversionRate — конверсия цели %

All reports include sessions + main goal metrics.
"""
STUB_MODE = True  # TODO: set False when real OAuth is configured
import requests
import random
from datetime import datetime, timedelta

METRIKA_STAT_URL = "https://api-metrika.yandex.net/stat/v1/data"


def _headers(token):
    return {"Authorization": f"OAuth {token}"}


def _base_metrics(goal_id=None):
    """Core metrics: sessions + goal or ecommerce revenue."""
    metrics = "ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:pageDepth,ym:s:avgVisitDurationSeconds"
    if goal_id:
        if goal_id == "ecommerce_revenue":
            metrics += ",ym:s:ecommerceRevenue,ym:s:ecommercePurchasedProducts"
        else:
            metrics += f",ym:s:goal{goal_id}reaches,ym:s:goal{goal_id}conversionRate"
    return metrics


def _date_range(days=30):
    """Return start_date and end_date in YYYY-MM-DD."""
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _stub_result(dimensions_count=1):
    """Generate realistic stub data for testing."""
    base = [random.randint(100, 5000), random.randint(50, 3000), round(random.uniform(20, 60), 1),
            round(random.uniform(1.5, 5.0), 1), random.randint(30, 300)]
    return {
        "totals": base,
        "rows": [
            {"dimensions": [f"item_{i}" for _ in range(dimensions_count)], "metrics": [max(1, v - i * 50) for v in base]}
            for i in range(5)
        ],
    }


def _query(token, counter_id, metrics, dimensions, days=30, limit=20, sort=None, filters=None):
    """Execute a Metrika stat query."""
    if STUB_MODE:
        return _stub_result()

    start_date, end_date = _date_range(days)
    params = {
        "ids": counter_id,
        "metrics": metrics,
        "dimensions": dimensions,
        "date1": start_date,
        "date2": end_date,
        "limit": limit,
        "lang": "ru",
    }
    if sort:
        params["sort"] = sort
    if filters:
        params["filters"] = filters

    resp = requests.get(METRIKA_STAT_URL, headers=_headers(token), params=params)
    resp.raise_for_status()
    data = resp.json()

    # Parse into structured format
    result = {"totals": data.get("totals", []), "rows": []}
    for row in data.get("data", []):
        dimensions_val = [d.get("name", d.get("id", "")) for d in row.get("dimensions", [])]
        metrics_val = row.get("metrics", [])
        result["rows"].append({"dimensions": dimensions_val, "metrics": metrics_val})
    return result


# ==========================================
# Report 1: Entry pages (страницы входа)
# ==========================================
def report_entry_pages(token, counter_id, goal_id=None, days=30, limit=15):
    """
    Страницы входа — с каких страниц начинают сессию.
    Показывает куда приходят люди и какие входные точки эффективны.
    """
    return _query(
        token, counter_id,
        metrics=_base_metrics(goal_id),
        dimensions="ym:s:startURL",
        days=days, limit=limit,
        sort="-ym:s:visits",
    )


# ==========================================
# Report 2: Traffic sources (источники)
# ==========================================
def report_sources(token, counter_id, goal_id=None, days=30):
    """
    Источники трафика — откуда приходят посетители.
    organic, direct, referral, social, ad, internal etc.
    """
    return _query(
        token, counter_id,
        metrics=_base_metrics(goal_id),
        dimensions="ym:s:sourceEngine",
        days=days, limit=20,
        sort="-ym:s:visits",
    )


# ==========================================
# Report 3: Search phrases / UTM terms (ключевые слова)
# ==========================================
def report_keywords(token, counter_id, goal_id=None, days=30, limit=30):
    """
    Поисковые фразы и UTM-terms.
    Показывает по каким запросам находят сайт.
    """
    # Search phrases from organic
    organic = _query(
        token, counter_id,
        metrics=_base_metrics(goal_id),
        dimensions="ym:s:searchPhrase",
        days=days, limit=limit,
        sort="-ym:s:visits",
        filters="ym:s:sourceEngine=='organic'",
    )
    return organic


# ==========================================
# Report 4: Day of week + Hour of day (дни недели и время суток)
# ==========================================
def report_day_hour(token, counter_id, goal_id=None, days=30):
    """
    Распределение трафика по дням недели и часам.
    Помогает понять когда аудитория активна.
    """
    # By day of week
    by_day = _query(
        token, counter_id,
        metrics=_base_metrics(goal_id),
        dimensions="ym:s:dayOfWeek",
        days=days, limit=7,
    )

    # By hour of day
    by_hour = _query(
        token, counter_id,
        metrics=_base_metrics(goal_id),
        dimensions="ym:s:hour",
        days=days, limit=24,
    )

    return {"by_day": by_day, "by_hour": by_hour}


# ==========================================
# Report 5: Cities (города)
# ==========================================
def report_cities(token, counter_id, goal_id=None, days=30, limit=20):
    """
    Города посетителей.
    Показывает географию аудитории.
    """
    return _query(
        token, counter_id,
        metrics=_base_metrics(goal_id),
        dimensions="ym:s:regionCity",
        days=days, limit=limit,
        sort="-ym:s:visits",
    )


# ==========================================
# Report 6: E-commerce funnel (воронка покупок)
# ==========================================
def report_ecommerce_funnel(token, counter_id, days=30):
    """
    Воронка e-commerce: от карточки товара до завершения заказа.
    Шаги: просмотр товара -> добавление в корзину -> начало оформления -> покупка
    """
    # Step-by-step: get visits at each funnel stage
    if STUB_MODE:
        return [
            {"step": "Просмотр товара", "value": 10000, "conversion": 100.0},
            {"step": "Просмотр карточки", "value": 4500, "conversion": 45.0},
            {"step": "Добавление в корзину", "value": 1200, "conversion": 26.7},
            {"step": "Начало оформления", "value": 600, "conversion": 50.0},
            {"step": "Покупка", "value": 280, "conversion": 46.7},
        ]

    steps = [
        ("Просмотр товара", "ym:s:productImpressions", "ym:s:productImpression"),
        ("Просмотр карточки", "ym:s:productClicks", "ym:s:productClick"),
        ("Добавление в корзину", "ym:s:productAddedToCartSteps", "ym:s:productAddToCart"),
        ("Начало оформления", "ym:s:productCheckoutStartedSteps", "ym:s:productBeginCheckout"),
        ("Покупка", "ym:s:productPurchasedSteps", "ym:s:productPurchase"),
    ]

    start_date, end_date = _date_range(days)
    funnel = []
    for step_name, metric, dimension in steps:
        params = {
            "ids": counter_id,
            "metrics": metric,
            "date1": start_date,
            "date2": end_date,
            "lang": "ru",
        }
        resp = requests.get(METRIKA_STAT_URL, headers=_headers(token), params=params)
        resp.raise_for_status()
        data = resp.json()
        value = data.get("totals", [0])[0]
        funnel.append({"step": step_name, "value": value})

    # Calculate conversion rates between steps
    for i in range(1, len(funnel)):
        prev = funnel[i - 1]["value"]
        curr = funnel[i]["value"]
        funnel[i]["conversion"] = round(curr / prev * 100, 1) if prev else 0
    funnel[0]["conversion"] = 100.0

    return funnel


# ==========================================
# Collect all reports
# ==========================================
def collect_all_reports(token, counter_id, goal_id=None, days=30):
    """Collect all reports at once."""
    reports = {
        "entry_pages": report_entry_pages(token, counter_id, goal_id, days),
        "sources": report_sources(token, counter_id, goal_id, days),
        "keywords": report_keywords(token, counter_id, goal_id, days),
        "day_hour": report_day_hour(token, counter_id, goal_id, days),
        "cities": report_cities(token, counter_id, goal_id, days),
    }
    # Always include ecommerce funnel
    reports["ecommerce_funnel"] = report_ecommerce_funnel(token, counter_id, days)
    return reports
