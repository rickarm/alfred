"""Checkout skill — end-of-day journal conversation."""

import json

from telegram.ext import (
    BaseHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from ..base import Skill
from . import flow


class CheckoutSkill(Skill):
    name = "checkout"
    description = "End-of-day journal checkout via guided conversation"

    def tools(self) -> list[dict]:
        return []

    async def execute_tool(self, name: str, tool_input: dict) -> str:
        return json.dumps({"error": "checkout skill has no tools"})

    def handlers(self) -> list[BaseHandler]:
        conv = ConversationHandler(
            entry_points=[CommandHandler("checkout", flow.start)],
            states={
                flow.ASK_HIGHLIGHT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, flow.got_highlight)
                ],
                flow.ASK_TOMORROW: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, flow.got_tomorrow)
                ],
            },
            fallbacks=[CommandHandler("cancel", flow.cancel)],
            conversation_timeout=600,
        )
        return [conv]

    def help_lines(self) -> list[str]:
        return ["/checkout — End-of-day journal (guided)"]
