"""REST endpoints that map to Things MCP tools."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import require_api_key
from ..mcp_client import call_tool

router = APIRouter(prefix="/api/v1")

Auth = Annotated[str, Depends(require_api_key)]

_LIST_TOOLS = {
    "inbox": "get_inbox",
    "today": "get_today",
    "upcoming": "get_upcoming",
    "anytime": "get_anytime",
    "someday": "get_someday",
    "logbook": "get_logbook",
    "trash": "get_trash",
}


def _ok(data: Any, *, source: str | None = None, count: int | None = None) -> dict:
    meta: dict = {"timestamp": datetime.now(UTC).isoformat()}
    if source is not None:
        meta["source"] = source
    if count is not None:
        meta["count"] = count
    elif isinstance(data, list):
        meta["count"] = len(data)
    return {"ok": True, "data": data, "meta": meta}


def _err(message: str) -> dict:
    return {
        "ok": False,
        "error": message,
        "meta": {"timestamp": datetime.now(UTC).isoformat()},
    }


async def _tool(tool_name: str, arguments: dict | None = None) -> list[dict]:
    try:
        return await call_tool(tool_name, arguments or {})
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health")
async def health() -> dict:
    try:
        await call_tool("get_today", {})
        return _ok({"status": "ok", "mcp": "connected"})
    except Exception as e:
        return _err(f"MCP unreachable: {e}")


# ---------------------------------------------------------------------------
# List views
# ---------------------------------------------------------------------------


@router.get("/lists/{list_name}")
async def get_list(_: Auth, list_name: str) -> dict:
    if list_name not in _LIST_TOOLS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown list '{list_name}'. Valid: {', '.join(_LIST_TOOLS)}",
        )
    data = await _tool(_LIST_TOOLS[list_name])
    return _ok(data, source=list_name)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@router.get("/projects")
async def get_projects(
    _: Auth,
    include_items: bool = Query(False),
) -> dict:
    data = await _tool("get_projects", {"include_items": include_items})
    return _ok(data)


@router.get("/projects/{uuid}/tasks")
async def get_project_tasks(_: Auth, uuid: str) -> dict:
    data = await _tool("get_todos", {"project_uuid": uuid})
    return _ok(data, source=f"project:{uuid}")


# ---------------------------------------------------------------------------
# Areas
# ---------------------------------------------------------------------------


@router.get("/areas")
async def get_areas(_: Auth) -> dict:
    data = await _tool("get_areas")
    return _ok(data)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


@router.get("/tags")
async def get_tags(_: Auth) -> dict:
    data = await _tool("get_tags")
    return _ok(data)


@router.get("/tags/{tag}/items")
async def get_tagged_items(_: Auth, tag: str) -> dict:
    data = await _tool("get_tagged_items", {"tag": tag})
    return _ok(data, source=f"tag:{tag}")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@router.get("/search")
async def search(_: Auth, q: str = Query(..., description="Search query")) -> dict:
    data = await _tool("search_todos", {"query": q})
    return _ok(data, source=f"search:{q}")


@router.get("/search/advanced")
async def search_advanced(
    _: Auth,
    status: str | None = Query(None),
    start_date: str | None = Query(None),
    deadline: str | None = Query(None),
    tag: str | None = Query(None),
    area: str | None = Query(None),
    type: str | None = Query(None),
    last: str | None = Query(None),
) -> dict:
    args = {
        k: v
        for k, v in {
            "status": status,
            "start_date": start_date,
            "deadline": deadline,
            "tag": tag,
            "area": area,
            "type": type,
            "last": last,
        }.items()
        if v is not None
    }
    data = await _tool("search_advanced", args)
    return _ok(data)


@router.get("/recent")
async def get_recent(
    _: Auth,
    period: str = Query("1d", description="Period e.g. 3d, 1w"),
) -> dict:
    data = await _tool("get_recent", {"period": period})
    return _ok(data, source=f"recent:{period}")


# ---------------------------------------------------------------------------
# Write — todos
# ---------------------------------------------------------------------------


@router.post("/todos")
async def add_todo(_: Auth, body: dict) -> dict:
    data = await _tool("add_todo", body)
    return _ok(data)


@router.patch("/todos/{id}")
async def update_todo(_: Auth, id: str, body: dict) -> dict:
    data = await _tool("update_todo", {"id": id, **body})
    return _ok(data)


# ---------------------------------------------------------------------------
# Write — projects
# ---------------------------------------------------------------------------


@router.post("/projects")
async def add_project(_: Auth, body: dict) -> dict:
    data = await _tool("add_project", body)
    return _ok(data)


@router.patch("/projects/{id}")
async def update_project(_: Auth, id: str, body: dict) -> dict:
    data = await _tool("update_project", {"id": id, **body})
    return _ok(data)
