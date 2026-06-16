"""Basic route tests using FastAPI TestClient with mocked MCP calls."""

import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.main import app
from src.config import settings

client = TestClient(app)
AUTH = {"Authorization": f"Bearer {settings.things_agent_api_key}"}

MOCK_TASKS = [
    {"title": "Buy milk", "uuid": "abc123", "type": "to_do", "status": "incomplete"}
]


def test_health_no_auth_required():
    # Liveness probe must not touch MCP — patch call_tool to blow up if it does.
    with patch(
        "src.routes.things.call_tool",
        new_callable=AsyncMock,
        side_effect=AssertionError("liveness probe must not call MCP"),
    ):
        r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "ok"


def test_health_ready_ok():
    with patch("src.routes.things.call_tool", new_callable=AsyncMock, return_value=MOCK_TASKS):
        r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["mcp"] == "connected"


def test_health_ready_reports_mcp_failure():
    with patch(
        "src.routes.things.call_tool",
        new_callable=AsyncMock,
        side_effect=RuntimeError("connection refused"),
    ):
        r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "MCP unreachable" in body["error"]


def test_health_ready_times_out_gracefully():
    async def _hang(*_args, **_kwargs):
        await asyncio.sleep(10)

    with patch("src.routes.things._READY_MCP_TIMEOUT", 0.05), patch(
        "src.routes.things.call_tool", new=_hang
    ):
        r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "did not respond" in body["error"]


def test_list_requires_auth():
    r = client.get("/api/v1/lists/today")
    assert r.status_code == 401


def test_list_today():
    with patch("src.routes.things.call_tool", new_callable=AsyncMock, return_value=MOCK_TASKS):
        r = client.get("/api/v1/lists/today", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["meta"]["source"] == "today"
    assert len(body["data"]) == 1


def test_list_unknown_returns_404():
    r = client.get("/api/v1/lists/doesnotexist", headers=AUTH)
    assert r.status_code == 404


def test_search():
    with patch("src.routes.things.call_tool", new_callable=AsyncMock, return_value=MOCK_TASKS):
        r = client.get("/api/v1/search?q=milk", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_projects():
    with patch("src.routes.things.call_tool", new_callable=AsyncMock, return_value=MOCK_TASKS):
        r = client.get("/api/v1/projects", headers=AUTH)
    assert r.status_code == 200


def test_areas():
    with patch("src.routes.things.call_tool", new_callable=AsyncMock, return_value=[]):
        r = client.get("/api/v1/areas", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["data"] == []
