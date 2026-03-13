"""Basic route tests using FastAPI TestClient with mocked MCP calls."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.config import settings

client = TestClient(app)
AUTH = {"Authorization": f"Bearer {settings.things_agent_api_key}"}

MOCK_TASKS = [
    {"title": "Buy milk", "uuid": "abc123", "type": "to_do", "status": "incomplete"}
]


def test_health_no_auth_required():
    with patch("src.routes.call_tool", new_callable=AsyncMock, return_value=MOCK_TASKS):
        r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_list_requires_auth():
    r = client.get("/api/v1/lists/today")
    assert r.status_code == 401


def test_list_today():
    with patch("src.routes.call_tool", new_callable=AsyncMock, return_value=MOCK_TASKS):
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
    with patch("src.routes.call_tool", new_callable=AsyncMock, return_value=MOCK_TASKS):
        r = client.get("/api/v1/search?q=milk", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_projects():
    with patch("src.routes.call_tool", new_callable=AsyncMock, return_value=MOCK_TASKS):
        r = client.get("/api/v1/projects", headers=AUTH)
    assert r.status_code == 200


def test_areas():
    with patch("src.routes.call_tool", new_callable=AsyncMock, return_value=[]):
        r = client.get("/api/v1/areas", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["data"] == []
