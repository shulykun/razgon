import requests


def get_search_queries(token, host_id):
    """Get top search queries from Webmaster."""
    # Stub
    return [
        {"query": "купить телефон", "impressions": 1200, "clicks": 85, "position": 3.2},
        {"query": "телефон москва", "impressions": 800, "clicks": 60, "position": 4.5},
        {"query": "смартфон недорого", "impressions": 600, "clicks": 40, "position": 5.1},
    ]


def get_crawl_errors(token, host_id):
    """Get crawl errors from Webmaster."""
    # Stub
    return {
        "404_errors": 12,
        "server_errors": 2,
        "broken_images": 5,
        "details": [
            {"url": "/old-page", "code": 404, "last_visited": "2026-04-28"},
            {"url": "/removed-product", "code": 404, "last_visited": "2026-04-27"},
        ],
    }


def get_indexing_status(token, host_id):
    """Get indexing stats."""
    # Stub
    return {
        "indexed_pages": 245,
        "excluded_pages": 30,
        "waiting_pages": 5,
    }
