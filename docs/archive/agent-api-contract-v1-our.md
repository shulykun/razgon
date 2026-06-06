# Razgon Agent API — Контракт интеграции

## Обзор

Razgon — сервис аналитики сайтов. Подключает Яндекс Метрику и Вебмастер, собирает данные, отправляет внешнему AI-агенту для генерации отчётов и ответов на вопросы пользователя.

**Схема работы:**
1. Пользователь подключает Яндекс OAuth → Razgon получает токен и данные счётчиков
2. Razgon собирает стандартные отчёты из Metrika/Webmaster API
3. Razgon отправляет всё агенту → агент генерирует персональный отчёт
4. Пользователь задаёт вопросы в чате → Razgon пересылает агенту → агент отвечает с контекстом проекта

**Вся коммуникация — асинхронная, через один endpoint.**

---

## Endpoint

```
POST /v1/messages
Content-Type: application/json
```

---

## Первое сообщение — инициация проекта и генерация отчёта

Отправляется один раз при создании проекта. Содержит токен Яндекса, цель пользователя и предсобранные отчёты.

### Запрос

```json
{
  "project_id": "uuid",
  "site_name": "example.ru",
  "goal": "Увеличить продажи в 2 раза за полгода",
  "yandex": {
    "token": "yandex_oauth_token",
    "metrika_counter_id": 123456,
    "webmaster_host_id": "https:example.ru:443"
  },
  "reports": [
    {
      "source": "metrika",
      "type": "traffic",
      "data": { ... }
    },
    {
      "source": "metrika",
      "type": "sources",
      "data": { ... }
    },
    {
      "source": "metrika",
      "type": "search_phrases",
      "data": { ... }
    },
    {
      "source": "metrika",
      "type": "landing_pages",
      "data": { ... }
    },
      {
      "source": "metrika",
      "type": "geo",
      "data": { ... }
    },
    {
      "source": "metrika",
      "type": "devices",
      "data": { ... }
    },
    {
      "source": "metrika",
      "type": "goals",
      "data": { ... }
    },
    {
      "source": "webmaster",
      "type": "indexing",
      "data": { ... }
    },
    {
      "source": "webmaster",
      "type": "search_queries",
      "data": { ... }
    }
  ]
}
```

### Логика на стороне агента

1. Сохранить `project_id`, `yandex.token`, все данные отчётов
2. Проанализировать данные: найти сильные/слабые стороны, точки роста, проблемы
3. При необходимости — дополнить анализ, сходив в API Метрики/Вебмастера самостоятельно по переданному токену
4. Сформировать отчёт по структуре (см. ниже «Структура отчёта»)
5. Отправить результат на callback Razgon'а

---

## Последующие сообщения — диалог

Отправляются при каждом сообщении пользователя в чате. Агент помнит контекст проекта и предыдущих сообщений.

### Запрос

```json
{
  "project_id": "uuid",
  "message": {
    "role": "user",
    "text": "А что с мобильным трафиком?"
  }
}
```

### Логика на стороне агента

1. Найти проект по `project_id`
2. Ответить с учётом контекста: данные отчётов, предыдущие сообщения, цель проекта
3. При необходимости — сходить в API Яндекса за доп. данными
4. Отправить ответ на callback Razgon'а

---

## Callback — ответ агента

Агент отправляет результат асинхронно на фиксированный URL:

```
POST https://razgon.roborumba.com/api/agent/callback
Content-Type: application/json
```

### Ответ на отчёт

```json
{
  "project_id": "uuid",
  "type": "report",
  "message": {
    "role": "assistant",
    "text": "## Полный отчёт по сайту example.ru\n\n### 1. Портрет клиента\n..."
  }
}
```

### Ответ на диалог

```json
{
  "project_id": "uuid",
  "type": "message",
  "message": {
    "role": "assistant",
    "text": "Мобильный трафик составляет 33% от общего, но bounce rate на мобильных 55%..."
  }
}
```

---

## Правила

| Правило | Описание |
|---------|----------|
| Один endpoint | Всё через `POST /v1/messages` |
| Различие по `reports` | Поле `reports` есть → инициация проекта, нет → диалог |
| Контекст у агента | Агент хранит все данные проекта и историю диалога по `project_id` |
| Токен Яндекса | Передаётся один раз при инициации, агент может использовать для доп. запросов к API |
| Callback фиксированный | `https://razgon.roborumba.com/api/agent/callback` — не передаётся в запросе |
| Асинхронность | Агент отвечает на callback когда готов, Razgon не ждёт синхронного ответа |
| Поля отчётов | Каждый отчёт содержит `source` (metrika/webmaster), `type` и `data` — данные в формате ответа соответствующего API Яндекса. Поля внутри `data` совпадают с полями API |

---

## API Яндекса (справочно)

Агент может использовать токен для самостоятельных запросов:

**Метрика:**
- `GET https://api-metrika.yandex.net/management/v1/counters` — список счётчиков
- `GET https://api-metrika.yandex.net/stat/v1/data` — статистика (аналог Analytics Reporting API)
- Заголовок: `Authorization: OAuth {token}`

**Вебмастер:**
- `GET https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/{host_id}/query-analytics` — поисковые запросы
- `GET https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/{host_id}/indexing-history` — история индексации
- Заголовок: `Authorization: OAuth {token}`
