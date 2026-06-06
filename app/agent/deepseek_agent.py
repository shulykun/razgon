"""Built-in agent using DeepSeek via vsegpt.ru for report generation."""

import json
import requests
import logging

logger = logging.getLogger(__name__)

API_URL = "https://api.deepseek.com/chat/completions"
API_KEY = "sk-6ff99adb03a144a0996d4ecc8b349a6a"
MODEL = "deepseek-chat"

SYSTEM_PROMPT = """Ты — SEO-аналитик и маркетолог. Проанализируй данные сайта и составь отчёт на русском языке.

Включи разделы:
1. 📊 Общая оценка сайта
2. 🔍 Поисковая видимость
3. ⚠️ Проблемы и ошибки
4. 📈 Рекомендации по улучшению
5. 🎯 Приоритетные действия

Пиши конкретно, с цифрами. Избегай общих фраз."""

OBJECTIVE_PROMPTS = {
    "sales": "Фокус на увеличении охвата и продаж. Рекомендуй каналы привлечения, точки роста, конверсионные улучшения.",
    "optimize": "Фокус на оптимизации рекламных расходов. Найди перерасход, неэффективные каналы, предложения по снижению CAC.",
    "efficiency": "Фокус на технической и контентной эффективности сайта. Найди проблемы с юзабилити, скоростью, контентом.",
    "audience": "Фокус на понимании аудитории. Проанализируй географию, поведение, сегменты, паттерны посещаемости.",
}

# Tools for the agent to request more data
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_metrika_traffic",
            "description": "Получить данные о трафике из Яндекс Метрики (посещения, посетители, просмотры по дням)",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Количество дней (по умолчанию 30)", "default": 30}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_metrika_sources",
            "description": "Получить данные об источниках трафика (поисковые системы, соцсети, прямой, реферальный)",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Количество дней", "default": 30}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_metrika_goals",
            "description": "Получить данные по конверсиям/целям из Метрики",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Количество дней", "default": 30}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_search_phrases",
            "description": "Получить поисковые запросы из Метрики — по каким фразам приходят из поиска",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Количество дней", "default": 30}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_webmaster_queries",
            "description": "Получить поисковые запросы из Яндекс Вебмастера — показы, клики, позиции",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_webmaster_indexing",
            "description": "Получить статус индексации сайта из Вебмастера",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
]


def _call_deepseek(messages, tools=None, max_tokens=4000):
    """Call DeepSeek API via vsegpt.ru."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    resp = requests.post(API_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


def generate_report(data, objective=None, goal=None):
    """Generate a report from collected data using DeepSeek.
    
    Args:
        data: dict with 'metrika' and 'webmaster' keys
        objective: one of sales/optimize/efficiency/audience
        goal: custom goal text
    
    Returns:
        str: generated report text
    """
    system_msg = SYSTEM_PROMPT
    
    if objective and objective in OBJECTIVE_PROMPTS:
        system_msg += f"\n\n{OBJECTIVE_PROMPTS[objective]}"
    if goal:
        system_msg += f"\n\n{goal}"

    # Summarize data to fit in context
    summary = _summarize_data(data)
    
    user_message = f"Данные сайта для анализа:\n\n{summary}"
    
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_message},
    ]
    
    try:
        result = _call_deepseek(messages)
        text = result["choices"][0]["message"]["content"]
        logger.info(f"DeepSeek report generated: {len(text)} chars")
        return text
    except Exception as e:
        logger.error(f"DeepSeek API error: {e}")
        return f"Ошибка генерации отчёта: {str(e)}"


def generate_report_with_tools(data, objective=None, goal=None):
    """Generate report using tool-calling agent approach.
    
    Sends initial data summary, lets agent request more details via tools.
    """
    system_msg = SYSTEM_PROMPT + "\n\nУ тебя есть инструменты для запроса дополнительных данных. Используй их если нужно больше деталей."
    if objective and objective in OBJECTIVE_PROMPTS:
        system_msg += f"\n\n{OBJECTIVE_PROMPTS[objective]}"
    if goal:
        system_msg += f"\n\n{goal}"

    summary = _summarize_data(data)
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": f"Данные сайта для анализа:\n\n{summary}"},
    ]
    
    max_rounds = 3
    for _ in range(max_rounds):
        result = _call_deepseek(messages, tools=TOOLS)
        choice = result["choices"][0]
        msg = choice["message"]
        
        # If no tool calls, return the text
        if not msg.get("tool_calls"):
            return msg["content"]
        
        # Process tool calls
        messages.append(msg)
        for tc in msg["tool_calls"]:
            tool_result = _execute_tool(tc["function"]["name"], tc["function"]["arguments"], data)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(tool_result, ensure_ascii=False) if isinstance(tool_result, dict) else str(tool_result),
            })
    
    # Final call without tools
    messages.append({"role": "user", "content": "Теперь составь финальный отчёт."})
    result = _call_deepseek(messages)
    return result["choices"][0]["message"]["content"]


def chat_with_context(project_id, message, data=None):
    """Chat about project data.
    
    Args:
        project_id: project id
        message: user question
        data: optional project data dict
    
    Returns:
        str: assistant response
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\nОтвечай кратко и по делу. Используй данные если они есть."},
    ]
    
    if data:
        messages.append({"role": "system", "content": f"Данные проекта:\n{_summarize_data(data)}"})
    
    # Load chat history
    from app.models import ChatMessage
    history = ChatMessage.query.filter_by(project_id=project_id).order_by(ChatMessage.id.desc()).limit(10).all()
    for hm in reversed(history):
        messages.append({"role": "user" if hm.role == "user" else "assistant", "content": hm.text})
    
    messages.append({"role": "user", "content": message})
    
    try:
        result = _call_deepseek(messages, max_tokens=2000)
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"DeepSeek chat error: {e}")
        return f"Ошибка: {str(e)}"


def _summarize_data(data):
    """Compress raw data into a concise summary for the prompt."""
    parts = []
    
    metrika = data.get("metrika", {})
    if metrika:
        # Traffic summary
        if "traffic" in metrika:
            traffic = metrika["traffic"]
            if isinstance(traffic, dict):
                parts.append(f"📊 ТРАФИК: {json.dumps(traffic, ensure_ascii=False)[:2000]}")
            elif isinstance(traffic, list):
                parts.append(f"📊 ТРАФИК ({len(traffic)} точек): {json.dumps(traffic[:30], ensure_ascii=False)[:2000]}")
        
        # Sources
        if "sources" in metrika:
            parts.append(f"🔗 ИСТОЧНИКИ: {json.dumps(metrika['sources'], ensure_ascii=False)[:1500]}")
        
        # Search phrases
        if "search_phrases" in metrika:
            parts.append(f"🔍 ПОИСКОВЫЕ ЗАПРОСЫ: {json.dumps(metrika['search_phrases'], ensure_ascii=False)[:1500]}")
        
        # Goals
        if "goals" in metrika:
            parts.append(f"🎯 КОНВЕРСИИ: {json.dumps(metrika['goals'], ensure_ascii=False)[:1000]}")
        
        # Geo
        if "geo" in metrika:
            parts.append(f"🌍 ГЕОГРАФИЯ: {json.dumps(metrika['geo'], ensure_ascii=False)[:1000]}")
        
        # Devices
        if "devices" in metrika:
            parts.append(f"📱 УСТРОЙСТВА: {json.dumps(metrika['devices'], ensure_ascii=False)[:800]}")
        
        # Landing pages
        if "landing_pages" in metrika:
            parts.append(f"📄 СТРАНИЦЫ ВХОДА: {json.dumps(metrika['landing_pages'], ensure_ascii=False)[:1000]}")
    
    webmaster = data.get("webmaster", {})
    if webmaster:
        if "indexing" in webmaster:
            parts.append(f"🗃️ ИНДЕКСАЦИЯ: {json.dumps(webmaster['indexing'], ensure_ascii=False)[:1000]}")
        if "search_queries" in webmaster:
            parts.append(f"🔎 ЗАПРОСЫ ВЕБМАСТЕРА: {json.dumps(webmaster['search_queries'], ensure_ascii=False)[:1500]}")
    
    if not parts:
        return "Данные отсутствуют."
    
    return "\n\n".join(parts)


def _execute_tool(name, args_str, data):
    """Execute a tool call by returning data from pre-collected dataset."""
    try:
        args = json.loads(args_str) if isinstance(args_str, str) else args_str
    except:
        args = {}
    
    metrika = data.get("metrika", {})
    webmaster = data.get("webmaster", {})
    
    tool_map = {
        "get_metrika_traffic": lambda: metrika.get("traffic", "Нет данных о трафике"),
        "get_metrika_sources": lambda: metrika.get("sources", "Нет данных об источниках"),
        "get_metrika_goals": lambda: metrika.get("goals", "Нет данных о целях"),
        "get_search_phrases": lambda: metrika.get("search_phrases", "Нет данных о поисковых запросах"),
        "get_webmaster_queries": lambda: webmaster.get("search_queries", "Нет данных вебмастера"),
        "get_webmaster_indexing": lambda: webmaster.get("indexing", "Нет данных об индексации"),
    }
    
    fn = tool_map.get(name)
    if fn:
        return fn()
    return f"Неизвестный инструмент: {name}"
