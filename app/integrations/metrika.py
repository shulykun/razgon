import requests


def get_traffic(token, counter_id, days=30):
    """Get traffic stats from Yandex Metrika."""
    # Stub
    return {
        "dates": ["2026-04-01", "2026-04-02", "2026-04-03"],
        "visits": [120, 145, 98],
        "users": [90, 110, 75],
    }


def get_sources(token, counter_id):
    """Get traffic sources breakdown."""
    # Stub
    return {
        "organic": 45,
        "direct": 20,
        "referral": 15,
        "social": 12,
        "paid": 8,
    }


def get_popular_pages(token, counter_id):
    """Get top pages by visits."""
    # Stub
    return [
        {"url": "/", "visits": 500, "bounce_rate": 35},
        {"url": "/catalog", "visits": 320, "bounce_rate": 42},
        {"url": "/about", "visits": 150, "bounce_rate": 55},
        {"url": "/contacts", "visits": 90, "bounce_rate": 60},
    ]
