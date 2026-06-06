"""Built-in agent using DeepSeek API with ReAct loop and real tool-calling."""

import json
import requests
import logging

logger = logging.getLogger(__name__)

API_URL = "https://api.deepseek.com/chat/completions"
API_KEY = "sk-6ff99adb03a144a0996d4ecc8b349a6a"
MODEL = "deepseek-chat"

SYSTEM_PROMPT = """Ты — аналитик цифрового маркетинга. Твоя задача — понять что происходит с сайтом и почему.

Ты работаешь в ReAct-цикле (Reason-Act). ПЕРВЫМ ДЕЛОМ вызови plan_analysis, чтобы сформулировать гипотезы и план проверки.
После плана выполняй шаги через query_metrika и query_webmaster.
Когда данных достаточно — верни текст отчёта.

Правила:
- Формат отчёта определяй сам исходя из задачи клиента
- Каждый вывод подкрепляй цифрами из данных
- Не просто пересказывай таблицы — объясняй ПОЧЕМУ
- Формулируй гипотезы и проверяй их данными
- Кросс-анализ: связывай разные срезы (аудитория × гео × время × источник)
- Рекомендации должны быть конкретными и приоритизированными (что делать в первую очередь)
- НЕ запрашивай данные с одинаковыми параметрами дважды
- Если инструмент вернул ошибку — не повторяй вызов, работай с имеющимися данными
- Все цифры бери ТОЛЬКО из полученных данных"""

OBJECTIVE_PROMPTS = {
    "sales": "Фокус на увеличении охвата и продаж. Рекомендуй каналы привлечения, точки роста, конверсионные улучшения.",
    "optimize": "Фокус на оптимизации рекламных расходов. Найди перерасход, неэффективные каналы, предложения по снижению CAC.",
    "efficiency": "Фокус на технической и контентной эффективности сайта. Найди проблемы с юзабилити, скоростью, контентом.",
    "audience": "Фокус на понимании аудитории. Проанализируй географию, поведение, сегменты, паттерны посещаемости.",
}

METRIKA_DIMENSIONS_DOC = """
Яндекс Метрика — dimensions (ym:s:*):
- ym:s:startURL — страница входа
- ym:s:sourceEngine — источник трафика
- ym:s:searchPhrase — поисковая фраза
- ym:s:regionCity — город
- ym:s:deviceCategory — тип устройства
- ym:s:gender — пол
- ym:s:ageInterval — возраст
- ym:s:dayOfWeek — день недели
- ym:s:hour — час дня
- ym:s:browser, ym:s:operatingSystem
- ym:s:UTMSource, ym:s:UTMMedium, ym:s:UTMCampaign

Яндекс Метрика — metrics (ym:s:*):
- ym:s:visits, ym:s:users, ym:s:bounceRate, ym:s:pageDepth
- ym:s:avgVisitDurationSeconds, ym:s:pageviews
- ym:s:goal<GOAL_ID>reaches, ym:s:goal<GOAL_ID>conversionRate

Сортировка: "-" перед метрикой = по убыванию.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "plan_analysis",
            "description": "Продумать стратегию анализа. Обязательно сформулируй гипотезы. Вызови первым шагом.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Описание задачи анализа"
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Название шага"},
                                "tool": {"type": "string", "description": "Какой инструмент использовать (query_metrika или query_webmaster)"},
                                "purpose": {"type": "string", "description": "Что узнаем"},
                                "params": {"type": "string", "description": "Ключевые параметры запроса (metrics, dimensions и т.д.)"}
                            },
                            "required": ["name", "tool", "purpose"]
                        },
                        "description": "План шагов анализа"
                    },
                    "hypotheses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Гипотезы которые стоит проверить"
                    }
                },
                "required": ["task", "steps", "hypotheses"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_metrika",
            "description": "Запрос к API Яндекс Метрики. Возвращает таблицу с данными.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metrics": {
                        "type": "string",
                        "description": "Метрики через запятую, например 'ym:s:visits,ym:s:users,ym:s:bounceRate'"
                    },
                    "dimensions": {
                        "type": "string",
                        "description": "Измерения через запятую, например 'ym:s:sourceEngine'"
                    },
                    "filters": {
                        "type": "string",
                        "description": "Фильтр (необязательно)"
                    },
                    "sort": {
                        "type": "string",
                        "description": "Сортировка (необязательно)"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Количество дней (по умолчанию 30)",
                        "default": 30
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Макс. строк (по умолчанию 20)",
                        "default": 20
                    }
                },
                "required": ["metrics", "dimensions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_webmaster",
            "description": "Запрос к API Яндекс Вебмастера. Получить данные по индексации, поисковым запросам, диагностике сайта.",
            "parameters": {
                "type": "object",
                "properties": {
                    "report_type": {
                        "type": "string",
                        "enum": ["search_queries", "indexing", "diagnostics", "summary"],
                        "description": "Тип отчёта: search_queries — поисковые запросы, indexing — статус индексации, diagnostics — проблемы, summary — сводка"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Количество дней (по умолчанию 30)",
                        "default": 30
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Макс. строк (по умолчанию 20)",
                        "default": 20
                    }
                },
                "required": ["report_type"]
            }
        }
    },
]


def _call_deepseek(messages, tools=None, max_tokens=4000):
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


def _query_metrika_api(token, counter_id, metrics, dimensions, filters=None, sort=None, days=30, limit=20, goal_id=None):
    """Execute a real Metrika stat API query."""
    from datetime import datetime, timedelta

    METRIKA_STAT_URL = "https://api-metrika.yandex.net/stat/v1/data"
    end = datetime.now()
    start = end - timedelta(days=days)

    params = {
        "ids": counter_id,
        "metrics": metrics,
        "dimensions": dimensions,
        "date1": start.strftime("%Y-%m-%d"),
        "date2": end.strftime("%Y-%m-%d"),
        "limit": limit,
        "lang": "ru",
    }
    if sort:
        params["sort"] = sort
    if filters:
        params["filters"] = filters

    resp = requests.get(
        METRIKA_STAT_URL,
        headers={"Authorization": f"OAuth {token}"},
        params=params,
    )
    resp.raise_for_status()
    data = resp.json()

    result = {"totals": data.get("totals", []), "rows": []}
    for row in data.get("data", []):
        dims = [d.get("name", d.get("id", "")) for d in row.get("dimensions", [])]
        metrics_val = row.get("metrics", [])
        result["rows"].append({"dimensions": dims, "metrics": metrics_val})

    result["row_count"] = len(result["rows"])
    result["rows"] = result["rows"][:50]
    return result


def _query_webmaster_api(token, host_id, report_type, days=30, limit=20):
    """Execute a real Webmaster API query."""
    from datetime import datetime, timedelta
    from urllib.parse import quote

    WM_API_URL = "https://api.webmaster.yandex.net/v4/user/hosts"

    headers = {"Authorization": f"OAuth {token}"}

    # Fix host_id format: ensure proper URL encoding
    if host_id:
        # If it looks like a raw host_id without proper encoding
        if "https:" in host_id and "//" not in host_id:
            # Format: https:xn--...:443 -> https://xn--...:443
            host_id = host_id.replace("https:", "https://", 1)
        # URL-encode the host_id for path usage
        encoded_host = quote(host_id, safe='')
    else:
        # Get first host from user's account
        resp = requests.get(WM_API_URL, headers=headers)
        resp.raise_for_status()
        hosts = resp.json().get("hosts", [])
        if not hosts:
            return {"error": "Нет сайтов в Вебмастере"}
        encoded_host = quote(hosts[0].get("host_id", ""), safe='')

    end = datetime.now()
    start = end - timedelta(days=days)

    base = f"{WM_API_URL}/{encoded_host}"

    try:
        if report_type == "summary":
            resp = requests.get(f"{base}/summary", headers=headers)
            resp.raise_for_status()
            return resp.json()

        elif report_type == "search_queries":
            params = {"date_from": start.strftime("%Y-%m-%d"), "date_to": end.strftime("%Y-%m-%d"), "limit": limit}
            resp = requests.get(f"{base}/search-queries", headers=headers, params=params)
            resp.raise_for_status()
            return {"queries": resp.json().get("queries", [])[:limit]}

        elif report_type == "indexing":
            resp = requests.get(f"{base}/indexing-history", headers=headers)
            resp.raise_for_status()
            return resp.json()

        elif report_type == "diagnostics":
            resp = requests.get(f"{base}/diagnostics", headers=headers)
            resp.raise_for_status()
            return resp.json()

        return {"error": f"Unknown report type: {report_type}"}
    except Exception as e:
        logger.error(f"Webmaster {report_type} failed: {e}")
        return {"error": str(e)}


def generate_report(data, objective=None, goal=None, token=None, counter_id=None, goal_id=None, webmaster_host_id=None):
    """Generate a report using ReAct loop with real tool-calling."""
    system_msg = SYSTEM_PROMPT
    if goal:
        system_msg = f"""⭐ ПРИОРИТЕТНАЯ ЗАДАЧА КЛИЕНТА:
{goal}

Это главная задача. Все рекомендации и анализ должны быть направлены на её решение.

""" + system_msg
    system_msg += f"\n\n{METRIKA_DIMENSIONS_DOC}"
    if goal_id:
        system_msg += f"\n\nID цели Метрики: {goal_id}. Используй ym:s:goal{goal_id}reaches и ym:s:goal{goal_id}conversionRate."
    if objective and objective in OBJECTIVE_PROMPTS:
        system_msg += f"\n\n{OBJECTIVE_PROMPTS[objective]}"

    summary = _summarize_data(data) if data else "Начальный контекст отсутствует, используй инструменты."

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": f"Данные сайта для анализа:\n\n{summary}"},
    ]

    # Dump full first request to file for debugging
    initial_payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "max_tokens": 4000,
        "temperature": 0.3,
        "tool_choice": "auto"
    }
    with open("/tmp/deepseek_request.json", "w") as f:
        json.dump(initial_payload, f, ensure_ascii=False, indent=2)
    logger.info("Full request dumped to /tmp/deepseek_request.json")

    def _safe_parse_args(args_str):
        """Parse tool args with fallback for malformed JSON."""
        if not isinstance(args_str, str):
            return args_str
        try:
            return json.loads(args_str)
        except json.JSONDecodeError:
            pass
        # Try to fix common issues: trailing commas, unquoted values
        import re
        fixed = args_str.strip()
        # Remove trailing comma before } or ]
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
        # Last resort: find the first valid JSON object
        for i in range(len(fixed)):
            if fixed[i] == '{':
                for j in range(len(fixed), i, -1):
                    try:
                        return json.loads(fixed[i:j])
                    except json.JSONDecodeError:
                        continue
                break
        logger.error(f"Failed to parse tool args: {args_str[:200]}")
        return {"_raw": args_str}

    def _exec_tool(name, args_str):
        args = _safe_parse_args(args_str)
        try:
            if name == "plan_analysis":
                steps = args.get("steps", [])
                hypotheses = args.get("hypotheses", [])
                logger.info(f"Agent plan ({len(steps)} steps): {[s.get('name','?') for s in steps]}")
                if hypotheses:
                    logger.info(f"Hypotheses: {hypotheses}")
                return {
                    "plan_accepted": True,
                    "steps_count": len(steps),
                    "steps": [{"name": s.get("name","?"), "tool": s.get("tool","?")} for s in steps],
                    "message": "План принят. Выполняй шаги через query_metrika / query_webmaster."
                }

            elif name == "query_metrika":
                metrics = args.get("metrics", "")
                dimensions = args.get("dimensions", "")
                if not metrics or not dimensions:
                    return {"error": "metrics и dimensions обязательны"}
                return _query_metrika_api(
                    token=token, counter_id=counter_id, goal_id=goal_id,
                    metrics=metrics, dimensions=dimensions,
                    filters=args.get("filters"), sort=args.get("sort"),
                    days=args.get("days", 30), limit=args.get("limit", 20),
                )

            elif name == "query_webmaster":
                return _query_webmaster_api(
                    token=token, host_id=webmaster_host_id,
                    report_type=args.get("report_type", "summary"),
                    days=args.get("days", 30), limit=args.get("limit", 20),
                )

            return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return {"error": str(e)}

    # ReAct loop
    max_rounds = 8
    for i in range(max_rounds):
        try:
            result = _call_deepseek(messages, tools=TOOLS)
        except Exception as e:
            logger.error(f"DeepSeek API error on round {i}: {e}")
            break

        choice = result["choices"][0]
        msg = choice["message"]

        # No tool calls = final answer
        if not msg.get("tool_calls"):
            logger.info(f"ReAct done in {i+1} rounds: {len(msg['content'])} chars")
            return msg["content"]

        # Execute tool calls
        messages.append(msg)
        for tc in msg["tool_calls"]:
            tool_result = _exec_tool(tc["function"]["name"], tc["function"]["arguments"])
            logger.info(f"  Tool {tc['function']['name']} -> {len(json.dumps(tool_result, ensure_ascii=False))} chars")
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(tool_result, ensure_ascii=False) if isinstance(tool_result, (dict, list)) else str(tool_result),
            })

    # Force final answer
    messages.append({"role": "user", "content": "Данных достаточно. Теперь составь финальный отчёт."})
    try:
        result = _call_deepseek(messages)
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"DeepSeek final call failed: {e}")
        return f"Ошибка генерации отчёта: {str(e)}"


def chat_with_context(project_id, message, data=None):
    """Chat about project data."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\nОтвечай кратко и по делу. Используй данные если они есть."},
    ]

    if data:
        messages.append({"role": "system", "content": f"Данные проекта:\n{_summarize_data(data)}"})

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
        if "traffic" in metrika:
            traffic = metrika["traffic"]
            if isinstance(traffic, list):
                parts.append(f"📊 ТРАФИК ({len(traffic)} точек): {json.dumps(traffic[:30], ensure_ascii=False)[:2000]}")
            else:
                parts.append(f"📊 ТРАФИК: {json.dumps(traffic, ensure_ascii=False)[:2000]}")
        if "sources" in metrika:
            parts.append(f"🔗 ИСТОЧНИКИ: {json.dumps(metrika['sources'], ensure_ascii=False)[:1500]}")
        if "search_phrases" in metrika:
            parts.append(f"🔍 ПОИСКОВЫЕ ЗАПРОСЫ: {json.dumps(metrika['search_phrases'], ensure_ascii=False)[:1500]}")
        if "goals" in metrika:
            parts.append(f"🎯 КОНВЕРСИИ: {json.dumps(metrika['goals'], ensure_ascii=False)[:1000]}")
        if "geo" in metrika:
            parts.append(f"🌍 ГЕОГРАФИЯ: {json.dumps(metrika['geo'], ensure_ascii=False)[:1000]}")
        if "devices" in metrika:
            parts.append(f"📱 УСТРОЙСТВА: {json.dumps(metrika['devices'], ensure_ascii=False)[:800]}")
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
