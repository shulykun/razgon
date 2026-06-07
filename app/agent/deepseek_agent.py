"""Built-in agent using DeepSeek API with ReAct loop and real tool-calling."""

import json
import requests
import logging

logger = logging.getLogger(__name__)

API_URL = "https://api.deepseek.com/chat/completions"
API_KEY = "sk-6ff99adb03a144a0996d4ecc8b349a6a"
MODEL = "deepseek-v4-flash"

# Track current agent step per project
_agent_steps = {}  # {project_id: {"round": N, "step": "текст"}}

def get_agent_step(project_id):
    return _agent_steps.get(project_id, {})

def set_agent_step(project_id, round_num, step_text):
    _agent_steps[project_id] = {"round": round_num, "step": step_text}

def _update_step_from_messages(project_id, round_num, messages):
    """Show a snippet of the last user/assistant message as the step."""
    # Find last assistant or tool message with content
    for msg in reversed(messages):
        content = msg.get("content", "")
        role = msg.get("role", "")
        if content and role in ("assistant", "user"):
            # First 120 chars, clean up
            snippet = content.replace("\n", " ").strip()[:1000]
            if len(content) > 1000:
                snippet += "..."
            set_agent_step(project_id, round_num, snippet)
            return
        elif role == "tool":
            # Show tool name from the content
            try:
                data = json.loads(content)
                if isinstance(data, dict) and data.get("query_type"):
                    set_agent_step(project_id, round_num, f"Получены данные: {data['query_type']}")
                    return
            except:
                pass
    set_agent_step(project_id, round_num, "Обработка...")

SYSTEM_PROMPT = """Ты — аналитик цифрового маркетинга. Анализируешь данные сайта и выдаёшь конкретный отчёт.

Ты работаешь в ReAct-цикле. ПЕРВЫМ ДЕЛОМ вызови plan_analysis с гипотезами.
После плана — выполняй шаги через query_metrika и query_webmaster.
Когда данных достаточно — верни текст финального отчёта.

## СТРУКТУРА ФИНАЛЬНОГО ОТЧЁТА

Отчёт должен состоять ровно из 5 разделов:

### 1. 🎯 Реализация цели клиента
Насколько сайт справляется с поставленной задачей? Текущие ключевые метрики. Есть ли прогресс?

### 2. 📊 Сравнение с рынком
Как показатели соотносятся с типичными значениями для аналогичных сайтов? Выше/ниже/в норме. Учитывай нишу, тип сайта, масштаб.

### 3. 🔍 Причины проблем
Что конкретно тянет вниз? Технические проблемы, контент, UX, источники трафика. Покажи цепочку «симптом → причина».

### 4. 💡 Что делать (приоритизировано)
Список действий от самого важного к наименее важному. Каждый пункт: что сделать + ожидаемый эффект. Не больше 7 пунктов.

### 5. 🧪 Гипотезы для проверки
3-5 проверяемых гипотез с описанием как их валидировать данными.

## ПРАВИЛА
- Отчёт КРАТКИЙ — каждый раздел 3-5 предложений + 1-2 таблицы/списка
- Не пересказывай данные — анализируй
- Все цифры ТОЛЬКО из полученных данных
- Кросс-анализ: связывай срезы (аудитория × гео × источник × время)
- Не запрашивай данные с одинаковыми параметрами дважды
- Если инструмент вернул ошибку — не повторяй, работай с имеющимися данными
- Для анализа конкурентов используй search_competitors — подбирай регион по географии трафика из Метрики
- Используй markdown: заголовки, **жирный**, таблицы, списки"""

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
- ym:s:visits, ym:s:bounceRate, ym:s:pageDepth
- ym:s:avgVisitDurationSeconds, ym:s:pageviews
- ym:s:goal<GOAL_ID>conversionRate

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
    {
        "type": "function",
        "function": {
            "name": "search_competitors",
            "description": "Поиск конкурентов через Яндекс. Возвращает список сайтов по запросу с заголовками и сниппетами. Используй для анализа конкурентного окружения, поиска аналогичных сервисов, сравнения позиций. ВАЖНО: ВСЕГДА добавляй главный город/регион из данных Метрики в текст запроса для локальных результатов (например: 'купить кондиционеры Владивосток', 'игра викторина Москва'). Без города в запросе результаты будут общероссийскими.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос (например: 'онлайн игра викторина' или 'сервис аналитики сайтов')"
                    },
                    "count": {
                        "type": "integer",
                        "description": "Количество результатов (по умолчанию 5, макс. 10)",
                        "default": 5
                    },
                    "region": {
                        "type": "string",
                        "description": "Регион поиска (необязательно). Название города или региона на русском: 'Москва', 'Владивосток', 'Россия', 'Краснодарский край' и т.д. По умолчанию все регионы.",
                        "default": ""
                    }
                },
                "required": ["query"]
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


def _search_competitors(query, count=5, region=None):
    """Search Yandex for competitor analysis."""
    import sys
    sys.path.insert(0, '/root/.openclaw/workspace/tools')
    from yandex_search import search as yandex_search
    
    # Map region name to Yandex region ID
    region_id = _resolve_region(region) if region else None
    
    results = yandex_search(query, count * 3, region=region_id)
    if isinstance(results, dict) and "error" in results:
        return results
    
    # Deduplicate by domain
    seen_domains = set()
    formatted = []
    from urllib.parse import urlparse
    for r in results:
        domain = urlparse(r.get("url", "")).netloc
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        formatted.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("snippet", ""),
        })
        if len(formatted) >= count:
            break
    
    return {"query": query, "region": region or "все регионы", "results": formatted, "total": len(formatted)}


def _resolve_region(name):
    """Map Russian region/city name to Yandex region ID."""
    if not name:
        return None
    # Try as numeric ID first
    if name.strip().isdigit():
        return name.strip()
    
    region_map = {
        # Cities
        'москва': '1', 'москве': '1', 'московская область': '1',
        'санкт-петербург': '2', 'петербург': '2', 'спб': '2', 'ленинградская область': '2',
        'новосибирск': '47', 'новосибирская область': '47',
        'екатеринбург': '54', 'свердловская область': '54',
        'казань': '65', 'татарстан': '65',
        'владивосток': '11073', 'приморский край': '11073',
        'краснодар': '10644', 'краснодарский край': '10644',
        'ростов-на-дону': '10115', 'ростовская область': '10115', 'ростов': '10115',
        'нижний новгород': '4775', 'нижегородская область': '4775',
        'самара': '5097', 'самарская область': '5097',
        'омск': '6498', 'омская область': '6498',
        'челябинск': '7385', 'челябинская область': '7385',
        'уфа': '8256', 'башкортостан': '8256',
        'воронеж': '4380', 'воронежская область': '4380',
        'красноярск': '9608', 'красноярский край': '9608',
        'пермь': '8266', 'пермский край': '8266',
        'волгоград': '10893', 'волгоградская область': '10893',
        'тюмень': '7386', 'тюменская область': '7386',
        'иркутск': '7387', 'иркутская область': '7387',
        'хабаровск': '7388', 'хабаровский край': '7388',
        'ярославль': '7389', 'ярославская область': '7389',
        'тверь': '7390', 'тверская область': '7390',
        'саратов': '7391', 'саратовская область': '7391',
        'тула': '7392', 'тульская область': '7392',
        'калуга': '7393', 'калужская область': '7393',
        'брянск': '7394', 'брянская область': '7394',
        'беларусь': '149', 'минск': '149',
        'украина': '187', 'киев': '187',
        'казахстан': '159', 'алматы': '159', 'астана': '159',
        # Countries
        'россия': '225', 'рф': '225',
        'крым': '11079', 'севастополь': '11079',
    }
    key = name.lower().strip()
    return region_map.get(key)


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

    # host_id is used as-is in the path (Yandex format: https:xn--...:443)
    # No encoding needed - requests handles it

    end = datetime.now()
    start = end - timedelta(days=days)

    base = f"{WM_API_URL}/{host_id}"

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


def generate_report(data, objective=None, goal=None, token=None, counter_id=None, goal_id=None, webmaster_host_id=None, project_id=None):
    """Generate a report using ReAct loop with real tool-calling."""
    system_msg = SYSTEM_PROMPT
    if goal:
        system_msg = f"""⭐ ПРИОРИТЕТНАЯ ЗАДАЧА КЛИЕНТА:
{goal}

Это главная задача. Все рекомендации и анализ должны быть направлены на её решение.

""" + system_msg
    system_msg += f"\n\n{METRIKA_DIMENSIONS_DOC}"
    if goal_id:
        system_msg += f"\n\nID цели Метрики: {goal_id}. Используй ym:s:goal{goal_id}conversionRate."
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

            elif name == "search_competitors":
                return _search_competitors(
                    query=args.get("query", ""),
                    count=min(args.get("count", 5), 10),
                    region=args.get("region"),
                )

            return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return {"error": str(e)}

    # ReAct loop
    max_rounds = 8
    for i in range(max_rounds):
        # Show last message context while waiting for API
        if project_id and messages:
            _update_step_from_messages(project_id, i+1, messages)
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
            if project_id:
                snippet = msg["content"].replace("\n", " ").strip()[:1000]
                if len(msg["content"]) > 1000:
                    snippet += "..."
                set_agent_step(project_id, i+1, f"📝 {snippet}")
            return msg["content"]

        # Execute tool calls
        messages.append(msg)
        for tc in msg["tool_calls"]:
            tool_name = tc["function"]["name"]
            tool_args_str = tc["function"]["arguments"]
            
            # Show meaningful step from tool arguments
            if project_id:
                try:
                    args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                except:
                    args = {}
                if tool_name == "plan_analysis":
                    hyps = args.get("hypotheses", [])
                    hyp_text = ", ".join(str(h)[:40] for h in hyps[:2])
                    set_agent_step(project_id, i+1, f"📋 Планирую: {hyp_text}")
                elif tool_name == "query_metrika":
                    dims = str(args.get("dimensions", ""))[:60]
                    set_agent_step(project_id, i+1, f"📊 Метрика: {dims}")
                elif tool_name == "query_webmaster":
                    rt = args.get("report_type", "summary")
                    set_agent_step(project_id, i+1, f"🔍 Вебмастер: {rt}")
                elif tool_name == "search_competitors":
                    q = args.get("query", "")[:50]
                    set_agent_step(project_id, i+1, f"🔎 Поиск конкурентов: {q}")
                else:
                    set_agent_step(project_id, i+1, f"⚙️ {tool_name}")
            
            tool_result = _exec_tool(tool_name, tool_args_str)
            logger.info(f"  Tool {tool_name} -> {len(json.dumps(tool_result, ensure_ascii=False))} chars")
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(tool_result, ensure_ascii=False) if isinstance(tool_result, (dict, list)) else str(tool_result),
            })

    # Force final answer
    if project_id:
        set_agent_step(project_id, max_rounds, "📝 Генерирую финальный отчёт...")
    messages.append({"role": "user", "content": "Данных достаточно. Составь финальный отчёт: 5 разделов (🎯 Цель | 📊 Рынок | 🔍 Причины | 💡 Действия ≤7 пунктов | 🧪 Гипотезы 3-5). Каждый раздел 3-5 предложений + 1 таблица. Без воды."})
    try:
        result = _call_deepseek(messages)
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"DeepSeek final call failed: {e}")
        return f"Ошибка генерации отчёта: {str(e)}"


def chat_with_context(project_id, message, data=None, report_text=None):
    """Chat about project data."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\nОтвечай кратко и по делу. Используй данные если они есть."},
    ]

    if data:
        messages.append({"role": "system", "content": f"Данные проекта:\n{_summarize_data(data)}"})

    if report_text:
        messages.append({"role": "system", "content": f"Сгенерированный отчёт:\n{report_text}"})

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


def _fmt_duration(seconds):
    """Format seconds to M:SS."""
    if seconds is None or seconds <= 0:
        return "0:00"
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}:{s:02d}"


def _strip_url(url, domain=""):
    """Remove protocol and domain from URL, keep path."""
    if not url:
        return url
    for prefix in ["https://", "http://"]:
        if url.startswith(prefix):
            url = url[len(prefix):]
            if "/" in url:
                url = url[url.index("/"):]
            else:
                url = "/"
            break
    return url


def _pct(val):
    """Format percentage."""
    if val is None:
        return "—"
    return f"{val:.1f}%"


def _compress_metrika_section(section_name, rows, totals, metrics_names=None):
    """Compress a metrika section with rows into compact text."""
    lines = []
    
    # Default metric mapping: [visits, bounce_rate, page_depth, avg_duration, goal_conversion]
    def extract(row):
        dims = row.get("dimensions", [])
        vals = row.get("metrics", [])
        name = dims[0] if dims else "?"
        visits = vals[0] if len(vals) > 0 else 0
        bounce = vals[1] if len(vals) > 1 else None
        depth = vals[2] if len(vals) > 2 else None
        duration = vals[3] if len(vals) > 3 else None
        conv = vals[4] if len(vals) > 4 else None
        return name, visits, bounce, depth, duration, conv
    
    if totals:
        t_visits = totals[0] if len(totals) > 0 else 0
        t_bounce = totals[1] if len(totals) > 1 else None
        t_depth = totals[2] if len(totals) > 2 else None
        t_duration = totals[3] if len(totals) > 3 else None
        t_conv = totals[4] if len(totals) > 4 else None
        
        parts = [f"Визиты: {int(t_visits)}"]
        if t_bounce is not None: parts.append(f"Отказы: {_pct(t_bounce)}")
        if t_depth is not None: parts.append(f"Глубина: {t_depth:.1f} стр")
        if t_duration is not None: parts.append(f"Время: {_fmt_duration(t_duration)}")
        if t_conv is not None: parts.append(f"Конверсия: {_pct(t_conv)}")
        lines.append(" | ".join(parts))
    
    for row in rows:
        name, visits, bounce, depth, duration, conv = extract(row)
        # Strip URLs for page sections
        if name.startswith("http"):
            name = _strip_url(name)
        # Skip rows with < 2 visits
        if isinstance(visits, (int, float)) and visits < 2:
            continue
        parts = [f"{name}: {int(visits)} виз"]
        if bounce is not None: parts.append(f"отказ {_pct(bounce)}")
        if conv is not None: parts.append(f"конверсия {_pct(conv)}")
        elif depth is not None: parts.append(f"{depth:.1f} стр")
        if duration is not None and duration > 0: parts.append(_fmt_duration(duration))
        lines.append(", ".join(parts))
    
    return "\n".join(lines)


def _summarize_data(data):
    """Compress raw data into compact structured text (~3x token reduction)."""
    if not data:
        return "Данные отсутствуют."
    
    sections = []
    metrika = data.get("metrika", {})
    
    if metrika:
        sections.append("=== МЕТРИКА (30 дней) ===")
        
        # Each section: check for totals + rows
        section_map = {
            "devices": "Устройства",
            "sources": "Источники",
            "cities": "Города",
            "demographics": "Демография",
            "entry_pages": "Страницы входа",
            "popular_pages": "Популярные страницы",
            "keywords": "Поисковые запросы",
            "day_hour": "По дням/часам",
        }
        
        for key, label in section_map.items():
            sec = metrika.get(key)
            if not sec:
                continue
            totals = sec.get("totals")
            rows = sec.get("rows", [])
            if not rows and not totals:
                continue
            compressed = _compress_metrika_section(label, rows, totals)
            sections.append(f"\n--- {label} ---")
            sections.append(compressed)
    
    webmaster = data.get("webmaster", {})
    if webmaster:
        sections.append("\n=== ВЕБМАСТЕР ===")
        
        summary = webmaster.get("summary")
        if summary:
            sqi = summary.get("sqi", "?")
            indexed = summary.get("indexed", "?")
            excluded = summary.get("excluded", "?")
            parts = [f"ИКС: {sqi} | В индексе: {indexed} | Исключено: {excluded}"]
            problems = summary.get("problems", {})
            if problems:
                parts.append(" | ".join(f"{k}: {v}" for k, v in problems.items()))
            sections.append("\n".join(parts))
        
        sq = webmaster.get("search_queries", {})
        if sq and sq.get("queries"):
            sections.append("\n--- Поисковые запросы ---")
            for q in sq["queries"][:15]:
                query = q.get("query", "?")
                shows = q.get("shows", "?")
                clicks = q.get("clicks", "?")
                pos = q.get("avg_position", q.get("position", "?"))
                sections.append(f'"{query}" — показы: {shows}, клики: {clicks}, поз: {pos}')
    
    if not sections:
        return "Данные отсутствуют."
    
    return "\n".join(sections)
