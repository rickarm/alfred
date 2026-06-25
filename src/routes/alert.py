"""POST /alert endpoint — receives state transitions from the service watcher."""

import logging
import time
from dataclasses import dataclass
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

# Services that never generate Telegram alerts (logged at INFO only).
_SILENT_SERVICES: frozenset[str] = frozenset(
    {"checkout-server", "things-export", "repo-sync", "sherlock-hq"}
)

# Group membership: maps any service name to a shared group key.
# All members share a single cooldown entry and display under the group key.
_SERVICE_GROUPS: dict[str, str] = {
    "openclaw": "openclaw",
    "openclaw-agent": "openclaw",
    "openclaw-functional-health": "openclaw",
}

_COOLDOWN_SECONDS = 30 * 60  # 30 minutes

# Numeric severity for state-worsening comparisons.
_STATE_SEVERITY: dict[str, int] = {"ok": 0, "degraded": 1, "down": 2}


@dataclass
class _CooldownEntry:
    last_alerted_at: float   # time.monotonic(); 0.0 = never alerted
    last_alerted_state: str  # to_state at the time of the last fired alert
    tracked_state: str       # most recent to_state received (may differ from alerted)


class AlertFilter:
    """Stateful filter that decides whether an incoming alert should fire."""

    def __init__(self) -> None:
        self._state: dict[str, _CooldownEntry] = {}

    def should_alert(self, service: str, transition: str) -> tuple[bool, str]:
        """Return (fire_alert, reason_string)."""
        if service in _SILENT_SERVICES:
            return False, f"{service!r} is in silent list"

        from_state, _, to_state = transition.partition("->")
        group_key = _SERVICE_GROUPS.get(service, service)
        is_grouped = service in _SERVICE_GROUPS

        entry = self._state.get(group_key)
        # Seed tracked_state from the payload's from_state when no history exists,
        # so a cold `down->ok` payload correctly identifies itself as a recovery.
        tracked_state = entry.tracked_state if entry else from_state
        last_alerted_state = entry.last_alerted_state if entry else from_state
        last_alerted_at = entry.last_alerted_at if entry else 0.0

        if to_state == "ok":
            # Info: only alert if the most-recently-tracked state was "down".
            fire = tracked_state == "down"
            reason = "recovery from down" if fire else f"recovery from {tracked_state!r} suppressed"

        elif to_state == "down" and not is_grouped:
            # Critical for standalone services: always fire immediately.
            fire = True
            reason = "critical"

        else:
            # Warning (→degraded) or grouped →down: cooldown-based.
            # "State worsens" is measured against the last *alerted* state so that
            # suppressed transitions don't silently lower the bar for re-alerting.
            if last_alerted_at == 0.0:
                fire = True
                reason = "first alert"
            else:
                to_sev = _STATE_SEVERITY.get(to_state, 1)
                alerted_sev = _STATE_SEVERITY.get(last_alerted_state, 0)
                if to_sev > alerted_sev:
                    fire = True
                    reason = f"state worsened: {last_alerted_state!r} → {to_state!r}"
                else:
                    elapsed = time.monotonic() - last_alerted_at
                    if elapsed >= _COOLDOWN_SECONDS:
                        fire = True
                        reason = "cooldown expired"
                    else:
                        fire = False
                        remaining = int(_COOLDOWN_SECONDS - elapsed)
                        reason = f"cooldown active ({remaining}s remaining)"

        self._state[group_key] = _CooldownEntry(
            last_alerted_at=time.monotonic() if fire else last_alerted_at,
            last_alerted_state=to_state if fire else last_alerted_state,
            tracked_state=to_state,
        )
        return fire, reason

    def _reset(self) -> None:
        self._state.clear()


_alert_filter = AlertFilter()


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
    fire, reason = _alert_filter.should_alert(body.service, body.transition)

    if not fire:
        logger.info(
            "Alert suppressed for %r (%s): %s", body.service, body.transition, reason
        )
        return {"ok": True, "suppressed": True, "reason": reason}

    from_state, _, to_state = body.transition.partition("->")
    icon = _TRANSITION_ICON.get(body.transition, "⚠️")
    label = to_state.upper() if to_state else body.transition.upper()

    # Grouped services display under the group key so multiple members read as one alert.
    display_name = _SERVICE_GROUPS.get(body.service, body.service)

    lines = [f"{icon} {label}: {display_name}"]
    lines.append(body.detail if body.detail else f"{from_state} → {to_state}")
    if to_state in ("down", "degraded"):
        lines.append(
            f"📄 <code>{body.log_file}</code>" if body.log_file else "📄 log path unavailable"
        )

    text = "\n".join(lines)
    return await _send_telegram(text)
