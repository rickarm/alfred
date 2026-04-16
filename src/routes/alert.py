"""POST /alert endpoint — receives state transitions from the service watcher."""

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import require_api_key
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

Auth = Annotated[str, Depends(require_api_key)]

_TRANSITION_ICON = {
    "ok->down": "🔴",
    "ok->degraded": "🟡",
    "degraded->down": "🔴",
    "down->ok": "🟢",
    "degraded->ok": "🟢",
}


class AlertPayload(BaseModel):
    service: str
    transition: str
    detail: str = ""
    log_tail: list[str] = []


async def _send_telegram(text: str) -> dict:
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.rick_chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload)
            data = r.json()
            if data.get("ok"):
                return {"ok": True, "telegram_message_id": data["result"]["message_id"]}
            return {"ok": False, "error": data.get("description", "Telegram API error")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/alert")
async def post_alert(_: Auth, body: AlertPayload) -> dict:
    from_state, _, to_state = body.transition.partition("->")
    icon = _TRANSITION_ICON.get(body.transition, "⚠️")
    label = to_state.upper() if to_state else body.transition.upper()

    lines = [
        f"{icon} {label}: {body.service}",
        f"{from_state} → {to_state}" if to_state else body.transition,
    ]
    if body.detail:
        lines.append(body.detail)

    truncated_tail = body.log_tail[-20:]
    if truncated_tail:
        lines.append("\nLast log lines:")
        lines.append("<pre>" + "\n".join(truncated_tail) + "</pre>")

    text = "\n".join(lines)
    return await _send_telegram(text)
