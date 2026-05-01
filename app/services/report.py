from app.integrations.metrika import get_traffic, get_sources, get_popular_pages
from app.integrations.webmaster import get_search_queries, get_crawl_errors, get_indexing_status
from app.agent.client import call_agent
import json


OBJECTIVE_PROMPTS = {
    "sales": "Фокус на увеличении охвата и продаж. Рекомендуй каналы привлечения, точки роста, конверсионные улучшения.",
    "optimize": "Фокус на оптимизации рекламных расходов. Найди перерасход, неэффективные каналы, предложения по снижению CAC.",
    "efficiency": "Фокус на технической и контентной эффективности сайта. Найди проблемы с юзабилити, скоростью, контентом.",
    "audience": "Фокус на понимании аудитории. Проанализируй географию, поведение, сегменты, паттерны посещаемости.",
}

SYSTEM_PROMPT = """Ты — SEO-аналитик и маркетолог. Проанализируй данные сайта и составь отчёт на русском языке.

Включи разделы:
1. 📊 Общая оценка сайта
2. 🔍 Поисковая видимость
3. ⚠️ Проблемы и ошибки
4. 📈 Рекомендации по улучшению
5. 🎯 Приоритетные действия

Пиши конкретно, с цифрами. Избегай общих фраз."""


def collect_data(token, counter_id, host_id):
    """Collect all data from Metrika + Webmaster."""
    return {
        "traffic": get_traffic(token, counter_id),
        "sources": get_sources(token, counter_id),
        "popular_pages": get_popular_pages(token, counter_id),
        "search_queries": get_search_queries(token, host_id),
        "crawl_errors": get_crawl_errors(token, host_id),
        "indexing": get_indexing_status(token, host_id),
    }


def generate_report(data, objective=None):
    """Send collected data to AI agent and get report."""
    objective_hint = OBJECTIVE_PROMPTS.get(objective, "") if objective else ""
    system_msg = SYSTEM_PROMPT
    if objective_hint:
        system_msg += f"\n\n{objective_hint}"

    user_message = f"Данные сайта для анализа:\n\n{json.dumps(data, ensure_ascii=False, indent=2)}"
    
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_message},
    ]
    
    return call_agent(messages)
