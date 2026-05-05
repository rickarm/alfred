"""Skill registry — aggregates tools and handlers from all registered skills."""

import json
import logging

from telegram.ext import BaseHandler

from .base import Skill

logger = logging.getLogger(__name__)


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: list[Skill] = []

    def register(self, skill: Skill) -> None:
        self._skills.append(skill)
        logger.info("Registered skill: %s", skill.name)

    def all_tools(self) -> list[dict]:
        return [t for skill in self._skills for t in skill.tools()]

    def all_handlers(self) -> list[BaseHandler]:
        return [h for skill in self._skills for h in skill.handlers()]

    def all_help_lines(self) -> list[str]:
        return [line for skill in self._skills for line in skill.help_lines()]

    async def execute_tool(self, name: str, tool_input: dict) -> str:
        for skill in self._skills:
            for tool in skill.tools():
                if tool["name"] == name:
                    return await skill.execute_tool(name, tool_input)
        logger.warning("Unknown tool requested: %s", name)
        return json.dumps({"error": f"Unknown tool: {name}"})
