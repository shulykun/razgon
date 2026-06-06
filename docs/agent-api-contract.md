# Razgon Agent API — Контракт интеграции (v2)

## Обзор

Razgon — сервис аналитики сайтов. Подключает Яндекс Метрику и Вебмастер, собирает данные, отправляет внешнему AI-агенту для генерации отчётов и ответов на вопросы пользователя.

**Схема работы:**
1. Пользователь подключает Яндекс OAuth → Razgon получает токен и данные счётчиков
2. Razgon собирает стандартные отчёты из Metrika/Webmaster API
3. Razgon отправляет всё агенту → агент генерирует персональный отчёт
4. Пользователь задаёт вопросы в чате → Razgon пересылает агенту → агент отвечает с контекстом проекта

**Вся коммуникация — асинхронная. HTTP-ответ подтверждает только приём задачи.**

---

## Endpoint

```http
POST https://api-k6pryiwyuq-as.a.run.app/v1/messages
Content-Type: application/json
x-razgon-token: <RAZGON_HTTP_TOKEN>
```

**Аутентификация:** заголовок `x-razgon-token` — обязателен для каждого запроса.

---

## 1. Init проекта / первый отчёт

Если в запросе есть поле `reports` (даже пустой массив) — это считается init-сценарием.

### Полный запрос

```json
{
  "project_id": "project-uuid",
  "site_name": "https://example.ru/",
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
      "data": {}
    },
    {
      "source": "webmaster",
      "type": "search_queries",
      "data": {}
    }
  ]
}
```

### Минимальный запрос (демо-режим без Яндекс-токена)

```json
{
  "project_id": "project-uuid",
  "site_name": "example.ru",
  "reports": []
}
```

### Обязательные поля

- `site_name` — домен или полный URL (агент нормализует до домена, определит протокол https → http → null)
- `reports` — массив, можно пустой `[]`

### Необязательные поля

- `project_id` — если не передан, агент сгенерирует свой. Но лучше всегда передавать стабильный ID
- `goal` — цель пользователя
- `yandex.token` — OAuth-токен Яндекса
- `yandex.metrika_counter_id` — ID счётчика Метрики
- `yandex.webmaster_host_id` — ID хоста в Вебмастере

### Работа без Яндекс-токена

Если `yandex.token` не передан:
- Агент не подключает инструменты Метрики и Вебмастера
- Отвечает по переданным `reports`, контексту проекта, истории диалога и публичным данным
- Если данных нет — честно сообщает об этом

### HTTP-ответ

```json
{
  "ok": true,
  "accepted": true,
  "job_id": "rz_project-uuid_...",
  "project_id": "project-uuid",
  "type": "report"
}
```

Финальный результат придёт callback-ом с `type: "report"`.

---

## 2. Диалог по существующему проекту

Если поле `reports` **отсутствует** — запрос считается вопросом пользователя.

### Запрос

```json
{
  "project_id": "project-uuid",
  "message": {
    "role": "user",
    "text": "Что с мобильным трафиком?"
  }
}
```

### Обязательные поля

- `project_id`
- `message.role` = `"user"`
- `message.text` — непустая строка

### HTTP-ответ

```json
{
  "ok": true,
  "accepted": true,
  "job_id": "rz_project-uuid_...",
  "project_id": "project-uuid",
  "type": "message"
}
```

Финальный результат придёт callback-ом с `type: "message"`.

### Маркер @context

Если в `message.text` есть маркер `@context` — агент подставит накопленный tool_context (результаты инструментов за последние 30 мин) в ответ.

```json
{
  "project_id": "project-uuid",
  "message": {
    "role": "user",
    "text": "@context сравни текущие выводы с предыдущей проверкой"
  }
}
```

---

## 3. Reports

Данные, которые Razgon собрал сам. Передаются при init.

Формат одного отчёта:

```json
{
  "source": "metrika",
  "type": "traffic",
  "data": {}
}
```

**source:** `metrika` | `webmaster`

**type:**
- `traffic` — трафик
- `sources` — источники
- `search_phrases` — поисковые фразы
- `landing_pages` — посадочные страницы
- `geo` — география
- `devices` — устройства
- `goals` — конверсии/цели
- `indexing` — индексация (Webmaster)
- `search_queries` — поисковые запросы (Webmaster)

Агент сохраняет reports как raw и передаёт в контекст.

---

## 4. Callback

Финальный ответ отправляется агентом асинхронно:

```http
POST https://razgon.roborumba.com/api/agent/callback
Content-Type: application/json
```

### Callback на отчёт

```json
{
  "project_id": "project-uuid",
  "type": "report",
  "message": {
    "role": "assistant",
    "text": "## Полный отчёт по сайту example.ru\n\n### 1. Портрет клиента\n..."
  },
  "project_context": {
    "isHuge": false,
    "reason": null,
    "context": {
      "niche": "Компания оказывает услуги...",
      "siteType": "services",
      "analyticsScheme": "страница услуги → интерес → заявка",
      "primaryGoals": ["заявка"],
      "supportingGoals": ["запрос консультации"],
      "reportSegments": ["частные и корпоративные клиенты"]
    }
  },
  "tool_context": {
    "text": "...",
    "text_chars": 12345,
    "expires_at": 1780060000000,
    "images_count": 0,
    "truncated": false
  }
}
```

### Callback на вопрос

```json
{
  "project_id": "project-uuid",
  "type": "message",
  "message": {
    "role": "assistant",
    "text": "Мобильный трафик составляет 33%..."
  },
  "tool_context": {
    "text": "...",
    "text_chars": 48231,
    "expires_at": 1780060000000,
    "images_count": 3,
    "truncated": false
  }
}
```

### Callback с ошибкой

```json
{
  "project_id": "project-uuid",
  "type": "error",
  "message": {
    "role": "assistant",
    "text": "Описание ошибки..."
  }
}
```

### Поля callback

| Поле | Описание |
|------|----------|
| `project_id` | ID проекта |
| `type` | `report` \| `message` \| `error` |
| `message.role` | Всегда `assistant` |
| `message.text` | Текст отчёта / ответа / ошибки |
| `project_context` | **Только для report.** Долгосрочный контекст: ниша, тип сайта, схема аналитики, цели |
| `tool_context` | Временный контекст инструментов (30 мин). Текст, размер, кол-во изображений |
| `tool_context.expires_at` | Unix timestamp (мс) когда контекст протухнет |
| `tool_context.truncated` | Был ли контекст обрезан |

Изображения, base64 и ссылки на storage в callback **не отправляются**. Только `images_count`.

---

## 5. HTTP-ошибки при отправке запроса

**Нет или неверный токен:**
```json
{
  "ok": false,
  "error": {
    "code": "FORBIDDEN",
    "message": "Invalid Razgon token."
  }
}
```

**Невалидный body для диалога:**
```json
{
  "ok": false,
  "error": {
    "code": "PROJECT_ID_REQUIRED",
    "message": "project_id обязателен для диалога."
  }
}
```

**Нет текста сообщения:**
```json
{
  "ok": false,
  "error": {
    "code": "MESSAGE_REQUIRED",
    "message": "Для диалога требуется message: {role:\"user\", text:string}."
  }
}
```

---

## 6. API Яндекса (справочно)

Агент может использовать OAuth-токен для самостоятельных запросов:

**Метрика:**
- `GET https://api-metrika.yandex.net/management/v1/counters` — список счётчиков
- `GET https://api-metrika.yandex.net/stat/v1/data` — статистика
- Заголовок: `Authorization: OAuth {token}`

**Вебмастер:**
- `GET https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/{host_id}/query-analytics` — поисковые запросы
- `GET https://api.webmaster.yandex.net/v4/user/{user_id}/hosts/{host_id}/indexing-history` — история индексации
- Заголовок: `Authorization: OAuth {token}`

---

## 7. Правила

| Правило | Описание |
|---------|----------|
| Один endpoint | Всё через `POST /v1/messages` |
| Аутентификация | `x-razgon-token` заголовок обязателен |
| `reports` есть → init | Init проекта + генерация отчёта |
| `reports` нет → dialogue | Вопрос пользователя по существующему проекту |
| Асинхронность | HTTP-ответ = подтверждение приёма, результат через callback |
| Яндекс-токены необязательны | Без токена — агент работает по reports + публичные данные |
| `project_context` | Генерируется агентом при init, приходит в callback |
| `tool_context` | Кешируется 30 мин, приходит в каждый callback |
| `@context` маркер | Включает tool_context в ответ |
| Callback фиксированный | `https://razgon.roborumba.com/api/agent/callback` |
