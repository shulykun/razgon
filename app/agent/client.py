import requests
import json
import logging
from app.config import Config

logger = logging.getLogger(__name__)


def send_project_init(project_id, site_name, reports, goal=None, yandex=None):
    """Send init request to agent API (async). Returns job_id or raises."""
    payload = {
        "project_id": str(project_id),
        "site_name": site_name,
        "reports": reports,
    }
    if goal:
        payload["goal"] = goal
    if yandex:
        payload["yandex"] = yandex

    # Dump request for debugging
    with open("/tmp/keng_request.json", "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"Full Keng request dumped to /tmp/keng_request.json")

    resp = requests.post(
        Config.AGENT_API_URL,
        headers={
            "Content-Type": "application/json",
            "x-razgon-token": Config.AGENT_RAZGON_TOKEN,
        },
        json=payload,
        timeout=30,
    )

    data = resp.json()
    if not data.get("ok"):
        error = data.get("error", {})
        logger.error(f"Agent init error: {error}")
        raise Exception(f"Agent error: {error.get('code', 'UNKNOWN')} — {error.get('message', '')}")

    logger.info(f"Agent accepted init for project {project_id}, job_id={data.get('job_id')}")
    return data


def send_chat_message(project_id, message_text):
    """Send chat message to agent API (async). Returns job_id or raises."""
    payload = {
        "project_id": str(project_id),
        "message": {
            "role": "user",
            "text": message_text,
        },
    }

    resp = requests.post(
        Config.AGENT_API_URL,
        headers={
            "Content-Type": "application/json",
            "x-razgon-token": Config.AGENT_RAZGON_TOKEN,
        },
        json=payload,
        timeout=30,
    )

    data = resp.json()
    if not data.get("ok"):
        error = data.get("error", {})
        logger.error(f"Agent chat error: {error}")
        raise Exception(f"Agent error: {error.get('code', 'UNKNOWN')} — {error.get('message', '')}")

    logger.info(f"Agent accepted chat for project {project_id}, job_id={data.get('job_id')}")
    return data
