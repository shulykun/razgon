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
import requests
from datetime import datetime, timedelta

METRIKA_STAT_URL = "https://api-metrika.yandex.net/stat/v1/data"


def _headers(token):
    return {"Authorization": f"OAuth {token}"}


def _base_metrics(goal_id=None):
    """Core metrics: sessions + goal if provided."""
    metrics = "ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:pageDepth,ym:s:avgVisitDurationSeconds"
    if goal_id:
        metrics += f",ym:s:goal{goal_id}reaches,ym:s:goal{goal_id}conversionRate"
    return metrics


def _date_range(days=30):
    """Return start_date and end_date in YYYY-MM-DD."""
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _query(token, counter_id, metrics, dimensions, days=30, limit=20, sort=None, filters=None):
    """Execute a Metrika stat query."""
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
# Collect all reports
# ==========================================
def collect_all_reports(token, counter_id, goal_id=None, days=30):
    """Collect all 5 reports at once."""
    return {
        "entry_pages": report_entry_pages(token, counter_id, goal_id, days),
        "sources": report_sources(token, counter_id, goal_id, days),
        "keywords": report_keywords(token, counter_id, goal_id, days),
        "day_hour": report_day_hour(token, counter_id, goal_id, days),
        "cities": report_cities(token, counter_id, goal_id, days),
    }
