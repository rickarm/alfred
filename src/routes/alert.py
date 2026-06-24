"""POST /alert endpoint — receives state transitions from the service watcher."""

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import require_api_key
from ..config import settings
from ..github_issues import maybe_file_issue

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
    log_file: str = ""
    log_tail: list[str] = []  # accepted for backwards compat; no longer rendered inline


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

    # ≤3 lines: headline, detail/transition, and a log-file pointer when down/degraded.
    lines = [f"{icon} {label}: {body.service}"]
    lines.append(body.detail if body.detail else f"{from_state} → {to_state}")
    if to_state in ("down", "degraded"):
        lines.append(
            f"📄 <code>{body.log_file}</code>" if body.log_file else "📄 log path unavailable"
        )

    text = "\n".join(lines)
    result = await _send_telegram(text)

    # Best-effort: file a GitHub issue for true outages. This never raises and never
    # blocks the alert — a filing failure leaves the Telegram result untouched.
    result["issue"] = await maybe_file_issue(body)
    return result
