"""Telegram bot — entry point and handlers."""

import logging

import httpx
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from . import agent, formatter
from .commands.services import cmd_logs, cmd_restart, cmd_services, cmd_status
from .config import settings

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _api_get(path: str, params: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {settings.things_agent_api_key}"}
    url = f"{settings.things_agent_base_url}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers=headers, params=params or {})
        return r.json()


async def _send(update: Update, text: str, parse_mode: str | None = ParseMode.HTML) -> None:
    """Send a message, falling back to plain text if parsing fails."""
    try:
        await update.message.reply_text(text, parse_mode=parse_mode)
    except Exception:
        # Fall back to plain text
        try:
            await update.message.reply_text(text, parse_mode=None)
        except Exception as e:
            logger.error("Failed to send message: %s", e)


def _log_user(update: Update) -> None:
    """Log every incoming user's ID — needed to set up TELEGRAM_ALLOWED_USER_IDS."""
    user = update.effective_user
    if user:
        logger.info(
            "Incoming message from user_id=%s username=@%s name='%s %s'",
            user.id,
            user.username or "",
            user.first_name or "",
            user.last_name or "",
        )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_user(update)
    text = (
        "<b>Alfred</b>\n\n"
        "<b>Things 3</b>\n"
        "/today — Today's tasks\n"
        "/inbox — Inbox\n"
        "/upcoming — Upcoming tasks\n"
        "/projects — All projects\n"
        "/areas — All areas\n"
        "/due — Tasks with deadline today or overdue\n"
        "/recent — Added in last 3 days\n"
        "/search &lt;term&gt; — Search tasks\n\n"
        "<b>Services</b>\n"
        "/services — List all services with status\n"
        "/status &lt;name&gt; — Service detail + last 10 log lines\n"
        "/restart &lt;name&gt; — Restart a service group\n"
        "/logs &lt;name&gt; [N] — Last N log lines (default 50, max 200)\n\n"
        "<b>Other</b>\n"
        "/help — This message\n\n"
        "Or just type naturally — I'll understand."
    )
    await _send(update, text)


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_user(update)
    resp = await _api_get("/lists/today")
    if resp.get("ok"):
        text = formatter.format_task_list(resp["data"], header=f"Today ({resp['meta']['count']})")
    else:
        text = f"Error: {resp.get('error', 'unknown')}"
    await _send(update, text)


async def cmd_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_user(update)
    resp = await _api_get("/lists/inbox")
    if resp.get("ok"):
        text = formatter.format_task_list(resp["data"], header=f"Inbox ({resp['meta']['count']})")
    else:
        text = f"Error: {resp.get('error', 'unknown')}"
    await _send(update, text)


async def cmd_upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_user(update)
    resp = await _api_get("/lists/upcoming")
    if resp.get("ok"):
        text = formatter.format_task_list(resp["data"], header=f"Upcoming ({resp['meta']['count']})")
    else:
        text = f"Error: {resp.get('error', 'unknown')}"
    await _send(update, text)


async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_user(update)
    resp = await _api_get("/projects")
    if resp.get("ok"):
        text = formatter.format_project_list(resp["data"])
    else:
        text = f"Error: {resp.get('error', 'unknown')}"
    await _send(update, text)


async def cmd_areas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_user(update)
    resp = await _api_get("/areas")
    if resp.get("ok"):
        text = formatter.format_area_list(resp["data"])
    else:
        text = f"Error: {resp.get('error', 'unknown')}"
    await _send(update, text)


async def cmd_due(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_user(update)
    from datetime import date
    today = date.today().isoformat()
    resp = await _api_get("/search/advanced", params={"deadline": today, "status": "incomplete"})
    if resp.get("ok"):
        text = formatter.format_task_list(resp["data"], header=f"Due today/overdue ({resp['meta']['count']})")
    else:
        text = f"Error: {resp.get('error', 'unknown')}"
    await _send(update, text)


async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_user(update)
    resp = await _api_get("/recent", params={"period": "3d"})
    if resp.get("ok"):
        text = formatter.format_task_list(resp["data"], header=f"Added last 3 days ({resp['meta']['count']})")
    else:
        text = f"Error: {resp.get('error', 'unknown')}"
    await _send(update, text)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_user(update)
    query = " ".join(context.args or []).strip()
    if not query:
        await _send(update, "Usage: /search &lt;keyword&gt;")
        return
    resp = await _api_get("/search", params={"q": query})
    if resp.get("ok"):
        text = formatter.format_search_results(resp["data"], query)
    else:
        text = f"Error: {resp.get('error', 'unknown')}"
    await _send(update, text)


# ---------------------------------------------------------------------------
# Natural language handler (Claude agent)
# ---------------------------------------------------------------------------


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _log_user(update)
    user_text = update.message.text or ""
    if not user_text.strip():
        return

    # Show typing indicator
    await update.message.chat.send_action("typing")

    response = await agent.run(user_text)

    # Agent returns plain text — send without parse mode to avoid formatting issues
    await _send(update, response, parse_mode=None)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("inbox", cmd_inbox))
    app.add_handler(CommandHandler("upcoming", cmd_upcoming))
    app.add_handler(CommandHandler("projects", cmd_projects))
    app.add_handler(CommandHandler("areas", cmd_areas))
    app.add_handler(CommandHandler("due", cmd_due))
    app.add_handler(CommandHandler("recent", cmd_recent))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("services", cmd_services))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting — polling for updates")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
