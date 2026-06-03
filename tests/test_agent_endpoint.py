"""Tests for the natural-language agent endpoint (POST /api/v1/message)."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.config import settings
from src.main import app

client = TestClient(app)
AUTH = {"Authorization": f"Bearer {settings.things_agent_api_key}"}


def test_message_requires_auth():
    r = client.post("/api/v1/message", json={"message": "add a task to buy milk"})
    assert r.status_code == 401


def test_message_runs_agent_and_returns_reply():
    reply = "Added 'Buy milk' to Today."
    with patch(
        "src.routes.agent.agent.run", new_callable=AsyncMock, return_value=reply
    ) as mock_run:
        r = client.post(
            "/api/v1/message",
            headers=AUTH,
            json={"message": "add a task to buy milk today"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["reply"] == reply
    assert "timestamp" in body["meta"]
    # The user's message is passed through to the agent loop.
    assert mock_run.await_args.args[0] == "add a task to buy milk today"


def test_message_validates_body():
    r = client.post("/api/v1/message", headers=AUTH, json={})
    assert r.status_code == 422
