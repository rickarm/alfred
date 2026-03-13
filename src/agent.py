"""Claude API agent with tool use for Things 3 operations."""

import json
import logging
from datetime import date

import anthropic
import httpx

from .config import settings
from .prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 8

_TOOLS: list[dict] = [
    {
        "name": "get_list",
        "description": "Get tasks from a Things 3 list. Use for: 'what's on my plate today', 'show inbox', 'what's upcoming'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "list_name": {
                    "type": "string",
                    "enum": ["inbox", "today", "upcoming", "anytime", "someday", "logbook"],
                    "description": "Which list to retrieve",
                }
            },
            "required": ["list_name"],
        },
    },
    {
        "name": "get_projects",
        "description": "Get all projects, optionally with their tasks. Use for: 'list my projects', 'show projects in Work area'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_items": {
                    "type": "boolean",
                    "description": "Include tasks within each project",
                }
            },
        },
    },
    {
        "name": "get_areas",
        "description": "Get all areas. Use for: 'show my areas', 'what areas do I have'.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_tasks",
        "description": "Search tasks by keyword in title or notes. Use for: 'find tasks about X', 'do I have a task for Y'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_advanced",
        "description": "Advanced search with filters. Use for: 'what's overdue', 'tasks tagged deepwork', 'tasks due this week'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["incomplete", "completed", "canceled"],
                },
                "deadline": {
                    "type": "string",
                    "description": "Deadline date YYYY-MM-DD or 'today'",
                },
                "tag": {"type": "string", "description": "Filter by tag name"},
                "area": {"type": "string", "description": "Filter by area UUID"},
                "last": {
                    "type": "string",
                    "description": "Recently created, e.g. '3d', '1w', '2m'",
                },
            },
        },
    },
    {
        "name": "get_recent",
        "description": "Get recently created items. Use for: 'what did I add recently', 'new tasks this week'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Time period like '3d', '1w', '2m'",
                }
            },
        },
    },
    {
        "name": "create_todo",
        "description": "Create a new task. Use for: 'add a task to...', 'remind me to...', 'create a todo for...'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "notes": {"type": "string", "description": "Task notes/details"},
                "when": {
                    "type": "string",
                    "description": "Schedule: 'today', 'tomorrow', 'evening', 'anytime', 'someday', or YYYY-MM-DD",
                },
                "deadline": {"type": "string", "description": "Due date YYYY-MM-DD"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags to apply",
                },
                "list_id": {
                    "type": "string",
                    "description": "Project UUID to add task to",
                },
                "checklist_items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Subtask checklist items",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "update_todo",
        "description": "Update an existing task — complete, reschedule, rename, cancel. IMPORTANT: search for the task first to get its UUID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Task UUID (find via search_tasks first)",
                },
                "title": {"type": "string"},
                "notes": {"type": "string"},
                "when": {
                    "type": "string",
                    "description": "Schedule: 'today', 'tomorrow', 'evening', 'anytime', 'someday', or YYYY-MM-DD",
                },
                "deadline": {"type": "string", "description": "Due date YYYY-MM-DD"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "completed": {
                    "type": "boolean",
                    "description": "Set to true to mark as complete",
                },
                "canceled": {
                    "type": "boolean",
                    "description": "Set to true to cancel",
                },
                "list_id": {
                    "type": "string",
                    "description": "Move to a different project",
                },
            },
            "required": ["id"],
        },
    },
    {
        "name": "create_project",
        "description": "Create a new project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Project title"},
                "notes": {"type": "string"},
                "when": {"type": "string"},
                "deadline": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "area_id": {
                    "type": "string",
                    "description": "Area UUID to place project in",
                },
            },
            "required": ["title"],
        },
    },
]


def _build_system_prompt() -> str:
    return SYSTEM_PROMPT.format(today=date.today().isoformat())


async def _call_api(method: str, path: str, **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {settings.things_agent_api_key}"}
    url = f"{settings.things_agent_base_url}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.request(method, url, headers=headers, **kwargs)
        return r.json()


async def _execute_tool(name: str, tool_input: dict) -> str:
    """Execute a tool call and return the result as a JSON string."""
    try:
        match name:
            case "get_list":
                result = await _call_api("GET", f"/lists/{tool_input['list_name']}")
            case "get_projects":
                params = {}
                if tool_input.get("include_items"):
                    params["include_items"] = "true"
                result = await _call_api("GET", "/projects", params=params)
            case "get_areas":
                result = await _call_api("GET", "/areas")
            case "search_tasks":
                result = await _call_api("GET", "/search", params={"q": tool_input["query"]})
            case "search_advanced":
                result = await _call_api("GET", "/search/advanced", params=tool_input)
            case "get_recent":
                period = tool_input.get("period", "3d")
                result = await _call_api("GET", "/recent", params={"period": period})
            case "create_todo":
                result = await _call_api("POST", "/todos", json=tool_input)
            case "update_todo":
                todo_id = tool_input.pop("id")
                result = await _call_api("PATCH", f"/todos/{todo_id}", json=tool_input)
            case "create_project":
                result = await _call_api("POST", "/projects", json=tool_input)
            case _:
                return json.dumps({"error": f"Unknown tool: {name}"})

        return json.dumps(result)

    except Exception as e:
        logger.exception("Tool execution failed: %s", name)
        return json.dumps({"error": str(e)})


def _extract_text(response) -> str:
    """Pull all text blocks from a Claude response."""
    parts = []
    for block in response.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts).strip()


async def run(user_message: str) -> str:
    """Send a user message through the Claude agent loop and return the response."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    messages: list[dict] = [{"role": "user", "content": user_message}]

    for turn in range(MAX_TOOL_CALLS):
        try:
            response = await client.messages.create(
                model=settings.claude_model,
                max_tokens=2048,
                system=_build_system_prompt(),
                tools=_TOOLS,
                messages=messages,
            )
        except anthropic.RateLimitError:
            return "Rate limit hit — try again in a moment."
        except anthropic.APIError as e:
            logger.exception("Anthropic API error")
            return f"Claude API error: {e}"

        if response.stop_reason == "end_turn":
            return _extract_text(response)

        if response.stop_reason != "tool_use":
            return _extract_text(response)

        # Add assistant's response (which includes tool_use blocks)
        messages.append({"role": "assistant", "content": response.content})

        # Execute all tool calls in this turn
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                logger.info("Tool call: %s(%s)", block.name, block.input)
                result_str = await _execute_tool(block.name, dict(block.input))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    }
                )

        messages.append({"role": "user", "content": tool_results})

    # Fell through max turns — return whatever text we have
    logger.warning("Reached max tool call turns (%d)", MAX_TOOL_CALLS)
    return _extract_text(response) or "Reached maximum tool call limit."
