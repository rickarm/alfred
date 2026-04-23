"""Shared Telegram utilities — guard, send, user logging."""

import logging

from telegram import Update
from telegram.constants import ParseMode

from .config import settings

logger = logging.getLogger(__name__)


def _allowed_ids() -> set[int]:
    raw = settings.telegram_allowed_user_ids.strip()
    if not raw:
        return set()
    return {int(uid.strip()) for uid in raw.split(",") if uid.strip()}


def log_user(update: Update) -> None:
    user = update.effective_user
    if user:
        logger.info(
            "msg from user_id=%s @%s '%s %s'",
            user.id,
            user.username or "",
            user.first_name or "",
            user.last_name or "",
        )


def is_allowed(update: Update) -> bool:
    allowed = _allowed_ids()
    if not allowed:
        return True
    user = update.effective_user
    return user is not None and user.id in allowed


async def guard(update: Update) -> bool:
    """Log the user; return False (silent drop) if not on the allow-list."""
    log_user(update)
    if not is_allowed(update):
        user = update.effective_user
        logger.warning("Rejected user_id=%s", user.id if user else "unknown")
        return False
    return True


async def send(update: Update, text: str, parse_mode: str | None = ParseMode.HTML) -> None:
    """Send a reply, falling back to plain text on parse errors."""
    try:
        await update.message.reply_text(text, parse_mode=parse_mode)
    except Exception:
        try:
            await update.message.reply_text(text, parse_mode=None)
        except Exception as e:
            logger.error("Failed to send message: %s", e)
