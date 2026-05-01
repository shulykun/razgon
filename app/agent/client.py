import requests
from app.config import Config


def call_agent(messages, model=None):
    """Call OpenAI-compatible agent API."""
    resp = requests.post(
        Config.AGENT_API_URL,
        headers={
            "Authorization": f"Bearer {Config.AGENT_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": model or Config.AGENT_MODEL,
            "messages": messages,
            "temperature": 0.7,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
