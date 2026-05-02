import requests
from app.config import Config


def call_agent(messages, model=None):
    """Call OpenAI-compatible agent API. Stub mode for now."""
    # TODO: switch to real agent when ready
    return (
        "## 📊 Анализ сайта\n\n"
        "Данные успешно собраны из Яндекс Метрики. "
        "Ниже представлена визуализация собранных данных.\n\n"
        "### 🔍 Краткие выводы\n\n"
        "- Основной трафик приходит из органического поиска\n"
        "- Рекомендуется усилить SEO-оптимизацию\n"
        "- Обратите внимание на страницы с высоким показателем отказов\n\n"
        "_Полноценный AI-анализ будет доступен после подключения агента._"
    )

    # Real agent call (uncomment when ready):
    # resp = requests.post(
    #     Config.AGENT_API_URL,
    #     headers={
    #         "Authorization": f"Bearer {Config.AGENT_API_KEY}",
    #         "Content-Type": "application/json",
    #     },
    #     json={
    #         "model": model or Config.AGENT_MODEL,
    #         "messages": messages,
    #         "temperature": 0.7,
    #     },
    #     timeout=60,
    # )
    # resp.raise_for_status()
    # return resp.json()["choices"][0]["message"]["content"]
