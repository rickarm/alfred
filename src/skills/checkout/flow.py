"""Checkout conversation flow — end-of-day journal via two-step dialogue."""

import logging
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from ...kb import append_entry
from ...tg import guard, send

logger = logging.getLogger(__name__)

# Conversation states
ASK_HIGHLIGHT = 1
ASK_TOMORROW = 2

_DATA_KEY = "checkout"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await guard(update):
        return ConversationHandler.END
    context.user_data[_DATA_KEY] = {}
    await send(
        update,
        "End-of-day checkout.\n\n<b>What was the highlight of today?</b>\n\n(Send /cancel to skip)",
    )
    return ASK_HIGHLIGHT


async def got_highlight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data[_DATA_KEY]["highlight"] = update.message.text.strip()
    await send(update, "<b>What's the most important thing for tomorrow?</b>")
    return ASK_TOMORROW


async def got_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data.get(_DATA_KEY, {})
    highlight = data.get("highlight", "")
    tomorrow = update.message.text.strip()

    entry = f"**Highlight:** {highlight}\n\n**Tomorrow:** {tomorrow}"
    path = append_entry(entry, tag="checkout")

    await send(
        update,
        f"Logged to <code>{path.name}</code> ✓",
    )
    context.user_data.pop(_DATA_KEY, None)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop(_DATA_KEY, None)
    await send(update, "Checkout cancelled.", parse_mode=None)
    return ConversationHandler.END
