"""Things 3 skill — slash commands and Claude tools for task management."""

import logging
from datetime import date

from telegram import Update
from telegram.ext import BaseHandler, CommandHandler, ContextTypes

from ... import formatter
from ...tg import guard, send
from ..base import Skill
from .executor import call_api
from .executor import execute_tool as _execute_tool
from .tools import THINGS_TOOLS

logger = logging.getLogger(__name__)


class ThingsSkill(Skill):
    name = "things"
    description = "Things 3 task management"

    # --- Claude integration ---

    def tools(self) -> list[dict]:
        return THINGS_TOOLS

    async def execute_tool(self, name: str, tool_input: dict) -> str:
        return await _execute_tool(name, tool_input)

    # --- Telegram command handlers ---

    async def _cmd_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        resp = await call_api("GET", "/lists/today")
        text = (
            formatter.format_task_list(resp["data"], header=f"Today ({resp['meta']['count']})")
            if resp.get("ok")
            else f"Error: {resp.get('error', 'unknown')}"
        )
        await send(update, text)

    async def _cmd_inbox(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        resp = await call_api("GET", "/lists/inbox")
        text = (
            formatter.format_task_list(resp["data"], header=f"Inbox ({resp['meta']['count']})")
            if resp.get("ok")
            else f"Error: {resp.get('error', 'unknown')}"
        )
        await send(update, text)

    async def _cmd_upcoming(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        resp = await call_api("GET", "/lists/upcoming")
        text = (
            formatter.format_task_list(resp["data"], header=f"Upcoming ({resp['meta']['count']})")
            if resp.get("ok")
            else f"Error: {resp.get('error', 'unknown')}"
        )
        await send(update, text)

    async def _cmd_projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        resp = await call_api("GET", "/projects")
        text = (
            formatter.format_project_list(resp["data"])
            if resp.get("ok")
            else f"Error: {resp.get('error', 'unknown')}"
        )
        await send(update, text)

    async def _cmd_areas(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        resp = await call_api("GET", "/areas")
        text = (
            formatter.format_area_list(resp["data"])
            if resp.get("ok")
            else f"Error: {resp.get('error', 'unknown')}"
        )
        await send(update, text)

    async def _cmd_due(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        today = date.today().isoformat()
        resp = await call_api(
            "GET", "/search/advanced", params={"deadline": today, "status": "incomplete"}
        )
        text = (
            formatter.format_task_list(
                resp["data"], header=f"Due today/overdue ({resp['meta']['count']})"
            )
            if resp.get("ok")
            else f"Error: {resp.get('error', 'unknown')}"
        )
        await send(update, text)

    async def _cmd_recent(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        resp = await call_api("GET", "/recent", params={"period": "3d"})
        text = (
            formatter.format_task_list(
                resp["data"], header=f"Added last 3 days ({resp['meta']['count']})"
            )
            if resp.get("ok")
            else f"Error: {resp.get('error', 'unknown')}"
        )
        await send(update, text)

    async def _cmd_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        query = " ".join(context.args or []).strip()
        if not query:
            await send(update, "Usage: /search &lt;keyword&gt;")
            return
        resp = await call_api("GET", "/search", params={"q": query})
        text = (
            formatter.format_search_results(resp["data"], query)
            if resp.get("ok")
            else f"Error: {resp.get('error', 'unknown')}"
        )
        await send(update, text)

    def handlers(self) -> list[BaseHandler]:
        return [
            CommandHandler("today", self._cmd_today),
            CommandHandler("inbox", self._cmd_inbox),
            CommandHandler("upcoming", self._cmd_upcoming),
            CommandHandler("projects", self._cmd_projects),
            CommandHandler("areas", self._cmd_areas),
            CommandHandler("due", self._cmd_due),
            CommandHandler("recent", self._cmd_recent),
            CommandHandler("search", self._cmd_search),
        ]

    def help_lines(self) -> list[str]:
        return [
            "/today — Today's tasks",
            "/inbox — Inbox",
            "/upcoming — Upcoming tasks",
            "/projects — All projects",
            "/areas — All areas",
            "/due — Tasks with deadline today or overdue",
            "/recent — Added in last 3 days",
            "/search &lt;term&gt; — Search tasks",
        ]
