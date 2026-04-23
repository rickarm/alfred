"""HTTP helpers for the Alfred REST gateway."""

import json
import logging

import httpx

from ...config import settings

logger = logging.getLogger(__name__)


async def call_api(method: str, path: str, **kwargs) -> dict:
    """Make an authenticated request to the Alfred REST gateway."""
    headers = {"Authorization": f"Bearer {settings.things_agent_api_key}"}
    url = f"{settings.alfred_base_url}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.request(method, url, headers=headers, **kwargs)
        return r.json()


async def execute_tool(name: str, tool_input: dict) -> str:
    """Execute a Things 3 tool call and return the result as a JSON string."""
    try:
        match name:
            case "get_list":
                result = await call_api("GET", f"/lists/{tool_input['list_name']}")
            case "get_projects":
                params = {}
                if tool_input.get("include_items"):
                    params["include_items"] = "true"
                result = await call_api("GET", "/projects", params=params)
            case "get_areas":
                result = await call_api("GET", "/areas")
            case "search_tasks":
                result = await call_api("GET", "/search", params={"q": tool_input["query"]})
            case "search_advanced":
                result = await call_api("GET", "/search/advanced", params=tool_input)
            case "get_recent":
                period = tool_input.get("period", "3d")
                result = await call_api("GET", "/recent", params={"period": period})
            case "create_todo":
                result = await call_api("POST", "/todos", json=tool_input)
            case "update_todo":
                body = dict(tool_input)
                todo_id = body.pop("id")
                result = await call_api("PATCH", f"/todos/{todo_id}", json=body)
            case "create_project":
                result = await call_api("POST", "/projects", json=tool_input)
            case _:
                return json.dumps({"error": f"Unknown tool: {name}"})
        return json.dumps(result)
    except Exception as e:
        logger.exception("Tool execution failed: %s", name)
        return json.dumps({"error": str(e)})
