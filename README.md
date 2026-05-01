# Razgon — AI-помощник для продвижения сайтов

## Идея

Веб-сервис, который помогает бизнесу улучшать свои сайты на основе реальных данных. Клиент подключает Яндекс Метрику и Яндекс Webmaster через OAuth, AI-агент анализирует данные и готовит персональный отчёт с рекомендациями. Затем можно уточнять задачи в чате.

## Пользовательский флоу

1. **Регистрация** — через Яндекс OAuth
2. **Подключение данных** — авторизация в Яндекс Метрике и Яндекс Webmaster
3. **Анализ** — AI-агент получает данные и генерирует базовый отчёт
4. **Чат** — уточнение задач, глубокие вопросы, планирование действий

## Стек

- **Backend:** Python (Flask)
- **Frontend:** JS, Bootstrap CSS
- **AI:** YandexGPT
- **Auth:** Яндекс OAuth
- **Data sources:** Яндекс Метрика API, Яндекс Webmaster API
- **DB:** SQLite (для начала)

## Интеграции

### Яндекс Метрика
- OAuth-авторизация
- Визиты, источники, поведенческие метрики
- Конверсии, цели, воронки

### Яндекс Webmaster
- OAuth-авторизация (тот же токен)
- Ошибки сканирования
- Поисковые запросы и позиции
- Индексация страниц

## Структура проекта

```
razgon/
├── app/
│   ├── __init__.py           # Flask app factory
│   ├── routes/
│   │   ├── auth.py           # Yandex OAuth
│   │   ├── dashboard.py      # Main dashboard
│   │   ├── chat.py           # Chat API
│   │   └── reports.py        # Report generation
│   ├── integrations/
│   │   ├── metrika.py        # Yandex Metrika API client
│   │   └── webmaster.py      # Yandex Webmaster API client
│   ├── agent/
│   │   └── analyzer.py       # AI agent logic
│   ├── models.py             # DB models (SQLAlchemy)
│   ├── templates/            # Jinja2 templates
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── dashboard.html
│   │   ├── chat.html
│   │   └── report.html
│   └── static/
│       ├── css/              # Bootstrap + custom
│       └── js/               # Vanilla JS
├── requirements.txt
├── config.py
├── run.py
├── Dockerfile
└── README.md
```

## MVP

1. Yandex OAuth авторизация
2. Подключение Метрики + Webmaster
3. Базовый AI-отчёт
4. Чат с контекстом данных сайта
