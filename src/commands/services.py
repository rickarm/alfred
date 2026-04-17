"""Telegram command handlers for service monitoring via Sherlock-HQ."""

import html
import logging

import httpx
from telegram import Update
from telegram.ext import ContextTypes

from ..config import settings

logger = logging.getLogger(__name__)

_STATUS_ICON = {"ok": "🟢", "degraded": "🟡", "down": "🔴"}


def _is_authorized(update: Update) -> bool:
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id != settings.rick_chat_id:
        logger.warning("Unauthorized service command from chat_id=%s", chat_id)
        return False
    return True


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.sherlock_dashboard_token}"}


def _esc(value) -> str:
    """HTML-escape for Telegram messages."""
    return html.escape(str(value)) if value is not None else ""


async def cmd_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{settings.sherlock_hq_url}/api/services", headers=_headers())
            r.raise_for_status()
            payload = r.json()
    except Exception as e:
        await update.message.reply_text(f"Error reaching Sherlock-HQ: {e}")
        return

    services = payload if isinstance(payload, list) else payload.get("services", [])
    counts: dict[str, int] = {"ok": 0, "degraded": 0, "down": 0}
    for svc in services:
        st = svc.get("status", "down")
        counts[st] = counts.get(st, 0) + 1

    header = (
        f"Mac mini services "
        f"({counts['ok']} ok · {counts['degraded']} degraded · {counts['down']} down)"
    )
    rows = []
    for svc in services:
        icon = _STATUS_ICON.get(svc.get("status", "down"), "⚫")
        name = _esc(svc.get("name", "?"))
        status = _esc(svc.get("status", "down"))
        detail = _esc(svc.get("detail", ""))
        rows.append(f"{icon} {name:<22} {status:<10} {detail}")

    text = f"{_esc(header)}\n\n<pre>" + "\n".join(rows) + "</pre>"
    await update.message.reply_text(text, parse_mode="HTML")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /status &lt;name&gt;")
        return
    name = args[0]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{settings.sherlock_hq_url}/api/services/{name}", headers=_headers()
            )
            if r.status_code == 404:
                await update.message.reply_text(f"Unknown service: {name}")
                return
            r.raise_for_status()
            svc = r.json()
    except httpx.HTTPStatusError as e:
        await update.message.reply_text(f"Error: {e}")
        return
    except Exception as e:
        await update.message.reply_text(f"Error reaching Sherlock-HQ: {e}")
        return

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            log_r = await client.get(
                f"{settings.sherlock_hq_url}/api/services/{name}/log",
                headers=_headers(),
                params={"tail": "10"},
            )
            log_data = log_r.json() if log_r.status_code == 200 else []
    except Exception:
        log_data = []

    log_lines = log_data if isinstance(log_data, list) else log_data.get("lines", [])
    icon = _STATUS_ICON.get(svc.get("status", "down"), "⚫")
    parts = [
        f"{icon} <b>{_esc(svc.get('name', name))}</b> — {_esc(svc.get('status', 'unknown'))}",
        f"Detail: {_esc(svc.get('detail', ''))}",
        f"Last OK: {_esc(svc.get('last_ok', 'never'))}",
        f"Last fail: {_esc(svc.get('last_fail', 'never'))}",
        f"Consecutive failures: {_esc(svc.get('consecutive_failures', 0))}",
    ]
    if log_lines:
        parts.append("\nLast 10 log lines:")
        parts.append(
            "<pre>" + "\n".join(_esc(line) for line in log_lines[-10:]) + "</pre>"
        )

    await update.message.reply_text("\n".join(parts), parse_mode="HTML")


async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /restart &lt;name&gt;")
        return
    name = args[0]

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{settings.sherlock_hq_url}/api/services/{name}/restart",
                headers=_headers(),
            )
            if r.status_code == 404:
                await update.message.reply_text(f"Unknown service: {name}")
                return
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        await update.message.reply_text(f"Error: {e}")
        return
    except Exception as e:
        await update.message.reply_text(f"Error reaching Sherlock-HQ: {e}")
        return

    results = data if isinstance(data, list) else data.get("results", [data])
    parts = ", ".join(
        f"{item.get('name', '?')} (exit {item.get('exit_code', '?')})" for item in results
    )
    await update.message.reply_text(f"→ restarted {parts}")


async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return

    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /logs &lt;name&gt; [N]")
        return
    name = args[0]
    try:
        n = min(int(args[1]), 200) if len(args) > 1 else 50
    except ValueError:
        n = 50

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{settings.sherlock_hq_url}/api/services/{name}/log",
                headers=_headers(),
                params={"tail": str(n)},
            )
            if r.status_code == 404:
                await update.message.reply_text(f"Unknown service: {name}")
                return
            r.raise_for_status()
            log_data = r.json()
    except httpx.HTTPStatusError as e:
        await update.message.reply_text(f"Error: {e}")
        return
    except Exception as e:
        await update.message.reply_text(f"Error reaching Sherlock-HQ: {e}")
        return

    log_lines = log_data if isinstance(log_data, list) else log_data.get("lines", [])
    if not log_lines:
        await update.message.reply_text(f"No logs found for {name}")
        return

    text = f"<b>Logs: {_esc(name)}</b> (last {len(log_lines)} lines)\n<pre>"
    text += "\n".join(_esc(line) for line in log_lines)
    text += "</pre>"
    if len(text) > 4000:
        text = text[:3990] + "\n…</pre>"
    await update.message.reply_text(text, parse_mode="HTML")
