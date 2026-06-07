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
- ym:s:goal<GOAL_ID>conversionRate — ТОЛЬКО если GOAL_ID это число!

ВАЖНО: не придумывай метрики! Используй ТОЛЬКО перечисленные выше.
Если цель не числовая — не используй goal... метрики.

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
    {
        "type": "function",
        "function": {
            "name": "query_wordstat",
            "description": "Яндекс Wordstat — статистика поисковых запросов. Возвращает топ похожих запросов и их частоту за 30 дней. Используй для оценки спроса, поиска новых ключевых слов, сравнения популярности фраз.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phrase": {
                        "type": "string",
                        "description": "Ключевая фраза для анализа"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Количество фраз в ответе. По умолчанию 20",
                        "default": 20
                    }
                },
                "required": ["phrase"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_page",
            "description": "Скрейпинг страницы сайта. Возвращает текстовое содержимое страницы (заголовки, текст, кнопки, формы). Используй для анализа реального контента сайта, проверки CTA, заголовков, структуры. Обязательно вызови для главной страницы анализируемого сайта.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL страницы для скрейпинга"
                    }
                },
                "required": ["url"]
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


def _scrape_page(url):
    """Scrape page content via Russian Web Proxy."""
    proxy_url = "http://45.90.34.46:8000/get-page-title"
    try:
        resp = requests.post(proxy_url, json={"url": url}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            return {"error": f"Scrape failed: {data.get('error', 'unknown')}"}

        from bs4 import BeautifulSoup
        source = data.get("source", "")
        if not source:
            return {"error": "Empty source"}

        soup = BeautifulSoup(source, "html.parser")

        # Remove script, style, nav, footer
        for tag in soup(["script", "style", "nav", "footer", "noscript"]):
            tag.decompose()

        result = {"url": url}

        # Title
        title = soup.find("title")
        if title:
            result["title"] = title.get_text(strip=True)

        # Meta description
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            result["meta_description"] = meta["content"][:200]

        # H1
        h1 = soup.find("h1")
        if h1:
            result["h1"] = h1.get_text(strip=True)

        # All H2s
        h2s = [h.get_text(strip=True) for h in soup.find_all("h2")]
        if h2s:
            result["h2"] = h2s[:10]

        # CTA buttons and links
        buttons = []
        for btn in soup.find_all(["button", "a"], class_=True):
            cls = " ".join(btn.get("class", []))
            if any(w in cls.lower() for w in ["btn", "cta", "button"]):
                buttons.append(btn.get_text(strip=True)[:60])
        if buttons:
            result["cta_buttons"] = buttons[:10]

        # Forms
        forms = soup.find_all("form")
        if forms:
            result["forms_count"] = len(forms)

        # Main text (limit to 2000 chars)
        body = soup.find("body") or soup
        text = body.get_text(separator=" ", strip=True)
        # Clean up whitespace
        import re
        text = re.sub(r"\s+", " ", text)
        result["text"] = text[:2000]

        return result
    except Exception as e:
        logger.error(f"Scrape failed for {url}: {e}")
        return {"error": str(e)}


def _query_wordstat_api(phrase, limit=20):
    """Query Yandex Wordstat API — top queries for a phrase (last 30 days)."""
    import os
    sys_path = os.path.expanduser("~/.openclaw/workspace/tools")
    if sys_path not in os.sys.path:
        os.sys.path.insert(0, sys_path)
    from yandex_search import get_iam_token

    iam_token, err = get_iam_token()
    if err:
        return {"error": f"IAM token error: {err}"}

    folder_id = os.environ.get("YANDEX_FOLDER_ID", "b1gplve2ue70hj8270mh")
    headers = {
        "Authorization": f"Bearer {iam_token}",
        "Content-Type": "application/json"
    }

    try:
        url = "https://searchapi.api.cloud.yandex.net/v2/wordstat/topRequests"
        body = {
            "phrase": phrase,
            "numPhrases": str(limit),
            "folderId": folder_id
        }
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results = [{"phrase": r.get("phrase", ""), "count": r.get("count", "0")} for r in data.get("results", [])[:limit]]
        associations = [{"phrase": r.get("phrase", ""), "count": r.get("count", "0")} for r in data.get("associations", [])[:10]]
        return {"total_count": data.get("totalCount", "0"), "top_queries": results, "associations": associations}
    except Exception as e:
        logger.error(f"Wordstat failed for '{phrase}': {e}")
        return {"error": str(e)}


def _query_webmaster_api(token, host_id, report_type, days=30, limit=20):
    """Execute a real Webmaster API query."""
    from datetime import datetime, timedelta
    from urllib.parse import quote

    # Get user ID first
    uid_resp = requests.get("https://api.webmaster.yandex.net/v4/user",
        headers={"Authorization": f"OAuth {token}"})
    uid_resp.raise_for_status()
    uid = uid_resp.json()["user_id"]

    headers = {"Authorization": f"OAuth {token}"}

    end = datetime.now()
    start = end - timedelta(days=days)

    base = f"https://api.webmaster.yandex.net/v4/user/{uid}/hosts/{host_id}"

    try:
        if report_type == "summary":
            resp = requests.get(f"{base}/summary", headers=headers)
            if resp.status_code == 404:
                return {"note": "Summary недоступен для этого хоста (возможно HTTP без HTTPS)"}
            resp.raise_for_status()
            return resp.json()

        elif report_type == "search_queries":
            resp = requests.get(f"{base}/search-queries/popular", headers=headers, params={"order_by": "TOTAL_SHOWS", "limit": limit})
            if resp.status_code == 404:
                return {"note": "Поисковые запросы недоступны для этого хоста"}
            resp.raise_for_status()
            queries = resp.json().get("queries", [])[:limit]
            # Extract just query text for cleaner output
            return {"queries": [q.get("query_text", q.get("query", "")) for q in queries]}

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
        if goal_id.isdigit():
            system_msg += f"\n\nID цели Метрики: {goal_id}. Используй метрику ym:s:goal{goal_id}conversionRate для конверсии."
        else:
            system_msg += f"\n\nЦель Метрики: {goal_id} (нечисловая, например ecommerce). Не используй ym:s:goal...conversionRate. Используй базовые метрики: visits, bounceRate, pageDepth, avgVisitDurationSeconds."
    if objective and objective in OBJECTIVE_PROMPTS:
        system_msg += f"\n\n{OBJECTIVE_PROMPTS[objective]}"

    # Don't pass data upfront — let agent use tools (true ReAct)
    site_info = ""
    if data:
        # Only pass minimal context: site URL, counter ID, what's available
        metrika_section = data.get("metrika", {})
        webmaster_section = data.get("webmaster", {})
        if metrika_section:
            site_info += f"Метрика: данные доступны (счётчик {counter_id})\n"
        if webmaster_section:
            site_info += f"Вебмастер: данные доступны\n"
    else:
        site_info = "Начальный контекст отсутствует, используй инструменты."

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": f"Проанализируй сайт. Доступные источники:\n{site_info}\n\nНачни с plan_analysis, затем запрашивай данные через инструменты."},
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

    # Track full ReAct trace
    trace_log = []
    def log_step(round_num, step_type, content):
        entry = {"round": round_num, "type": step_type, "content": content[:500] if isinstance(content, str) else str(content)[:500]}
        trace_log.append(entry)
        # Write immediately so we can debug even if thread crashes
        with open("/tmp/deepseek_trace.json", "w") as f:
            json.dump(trace_log, f, ensure_ascii=False, indent=2)

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

            elif name == "query_wordstat":
                return _query_wordstat_api(
                    phrase=args.get("phrase", ""),
                    limit=args.get("limit", 20),
                )

            elif name == "scrape_page":
                return _scrape_page(args.get("url", ""))

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
    max_rounds = 10
    for i in range(max_rounds):
        # Show last message context while waiting for API response
        if project_id and messages:
            current = get_agent_step(project_id)
            if current.get("round") != i+1:
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
            log_step(i+1, "final_answer", msg["content"])
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
                elif tool_name == "query_wordstat":
                    ph = args.get("phrase", "")[:40]
                    set_agent_step(project_id, i+1, f"📈 Wordstat: {ph}")
                elif tool_name == "scrape_page":
                    u = args.get("url", "")[:50]
                    set_agent_step(project_id, i+1, f"🕷️ Скрейпинг: {u}")
                else:
                    set_agent_step(project_id, i+1, f"⚙️ {tool_name}")
            
            tool_result = _exec_tool(tool_name, tool_args_str)
            logger.info(f"  Tool {tool_name} -> {len(json.dumps(tool_result, ensure_ascii=False))} chars")
            log_step(i+1, f"tool:{tool_name}", tool_result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(tool_result, ensure_ascii=False) if isinstance(tool_result, (dict, list)) else str(tool_result),
            })

        # Compress old messages after round 5 to save context
        if i >= 5 and len(messages) > 10:
            messages = _compress_messages(messages)

    # Force final answer
    if project_id:
        set_agent_step(project_id, max_rounds, "📝 Генерирую финальный отчёт...")
    with open("/tmp/deepseek_trace.json", "w") as f:
        json.dump(trace_log, f, ensure_ascii=False, indent=2)
        logger.info(f"Trace dumped to /tmp/deepseek_trace.json ({len(trace_log)} steps)")

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


def _compress_messages(messages, keep_recent=6):
    """Compress old messages: keep assistant reasoning + tool summaries, drop raw data rows."""
    if len(messages) <= keep_recent + 1:
        return messages
    
    system_msgs = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]
    
    old_msgs = non_system[:-keep_recent]
    recent_msgs = non_system[-keep_recent:]
    
    compressed_old = []
    for m in old_msgs:
        role = m.get("role", "")
        content_str = m.get("content", "")
        
        if role == "assistant":
            # Keep reasoning, truncate if very long
            if len(content_str) > 800:
                compressed_old.append({"role": "assistant", "content": content_str[:800] + "\n...[обрезано]"})
            else:
                compressed_old.append(m)
        
        elif role == "tool":
            # Keep tool result but truncate raw data
            try:
                data = json.loads(content_str)
                compressed_data = _truncate_tool_data(data, max_rows=5)
                compressed_old.append({"role": "tool", "tool_call_id": m.get("tool_call_id", ""), "content": json.dumps(compressed_data, ensure_ascii=False)})
            except:
                compressed_old.append({"role": "tool", "tool_call_id": m.get("tool_call_id", ""), "content": content_str[:500]})
        
        else:
            compressed_old.append(m)
    
    result = system_msgs + compressed_old + recent_msgs
    old_chars = sum(len(m.get("content","")) for m in old_msgs)
    new_chars = sum(len(m.get("content","")) for m in compressed_old)
    logger.info(f"Compressed messages: {len(messages)} msgs, old chars: {old_chars} -> {new_chars}")
    return result


def _truncate_tool_data(data, max_rows=5):
    """Truncate long lists/rows in tool results, keep structure and totals."""
    if isinstance(data, list):
        if len(data) <= max_rows:
            return data
        return data[:max_rows] + [{"...": f"ещё {len(data) - max_rows} записей"}]
    
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if isinstance(v, list) and len(v) > max_rows:
                result[k] = v[:max_rows] + [{"...": f"ещё {len(v) - max_rows} записей"}]
            elif isinstance(v, dict):
                result[k] = _truncate_tool_data(v, max_rows)
            else:
                result[k] = v
        return result
    
    return data


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
