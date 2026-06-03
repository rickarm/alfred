"""Telegram bot — entry point and handlers."""

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from . import agent
from .commands.services import cmd_logs, cmd_restart, cmd_services, cmd_status
from .config import settings
from .skills import registry
from .tg import guard, send

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


_SERVICES_HELP = [
    "/services — List all services with status",
    "/status &lt;name&gt; — Service detail + last 10 log lines",
    "/restart &lt;name&gt; — Restart a service group",
    "/logs &lt;name&gt; [N] — Last N log lines (default 50, max 200)",
]


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    skill_lines = "\n".join(registry.all_help_lines())
    services_lines = "\n".join(_SERVICES_HELP)
    text = (
        "<b>Alfred</b>\n\n"
        "<b>Things 3</b>\n"
        f"{skill_lines}\n\n"
        "<b>Services</b>\n"
        f"{services_lines}\n\n"
        "<b>Other</b>\n"
        "/help — This message\n\n"
        "Or just type naturally — I'll understand and make the change in Things."
    )
    await send(update, text)


# ---------------------------------------------------------------------------
# Natural language handler (Claude agent)
# ---------------------------------------------------------------------------


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard(update):
        return
    user_text = update.message.text or ""
    if not user_text.strip():
        return

    # Show typing indicator
    await update.message.chat.send_action("typing")

    response = await agent.run(user_text, registry.all_tools(), registry.execute_tool)

    # Agent returns plain text — send without parse mode to avoid formatting issues
    await send(update, response, parse_mode=None)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    app = Application.builder().token(settings.telegram_bot_token).build()

    # Skill handlers (Things slash commands + checkout conversation). Registered
    # before the catch-all MessageHandler so an active conversation keeps priority.
    for handler in registry.all_handlers():
        app.add_handler(handler)

    # Help
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("help", cmd_help))

    # Service monitoring commands (proxied to Sherlock-HQ)
    app.add_handler(CommandHandler("services", cmd_services))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_handler(CommandHandler("logs", cmd_logs))

    # Free-text → Claude agent → Things edits
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting — polling for updates")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
