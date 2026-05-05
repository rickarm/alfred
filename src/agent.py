"""Claude API agent loop."""

import logging
from collections.abc import Awaitable, Callable
from datetime import date

import anthropic

from .config import settings
from .prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 8


def _build_system_prompt() -> str:
    return SYSTEM_PROMPT.format(today=date.today().isoformat())


def _extract_text(response) -> str:
    return "\n".join(
        block.text for block in response.content if hasattr(block, "text")
    ).strip()


async def run(
    user_message: str,
    tools: list[dict],
    execute_tool: Callable[[str, dict], Awaitable[str]],
) -> str:
    """Run the Claude agent loop and return the final text response."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    messages: list[dict] = [{"role": "user", "content": user_message}]

    for _ in range(MAX_TOOL_CALLS):
        try:
            response = await client.messages.create(
                model=settings.claude_model,
                max_tokens=2048,
                system=_build_system_prompt(),
                tools=tools,
                messages=messages,
            )
        except anthropic.RateLimitError:
            return "Rate limit hit — try again in a moment."
        except anthropic.APIError as e:
            logger.exception("Anthropic API error")
            return f"Claude API error: {e}"

        if response.stop_reason != "tool_use":
            return _extract_text(response)

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                logger.info("Tool call: %s(%s)", block.name, block.input)
                result = await execute_tool(block.name, dict(block.input))
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                )

        messages.append({"role": "user", "content": tool_results})

    logger.warning("Reached max tool call turns (%d)", MAX_TOOL_CALLS)
    return _extract_text(response) or "Reached maximum tool call limit."
