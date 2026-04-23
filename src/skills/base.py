"""Base class for Alfred skills."""

from abc import ABC, abstractmethod

from telegram.ext import BaseHandler


class Skill(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    def tools(self) -> list[dict]:
        """Claude tool definitions provided by this skill."""

    @abstractmethod
    async def execute_tool(self, name: str, tool_input: dict) -> str:
        """Execute a named tool. Must handle all tools returned by tools()."""

    @abstractmethod
    def handlers(self) -> list[BaseHandler]:
        """Telegram handlers provided by this skill."""

    def help_lines(self) -> list[str]:
        """Lines to include in /help output. Override to document commands."""
        return []
