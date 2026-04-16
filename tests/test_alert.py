"""Tests for POST /alert endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.config import settings
from src.main import app

client = TestClient(app)
AUTH = {"Authorization": f"Bearer {settings.things_agent_api_key}"}

VALID_PAYLOAD = {
    "service": "sherlock-hq",
    "transition": "ok->down",
    "detail": "HTTP 000 (timeout after 5s)",
    "log_tail": ["line1", "line2"],
}


def _mock_telegram_success(message_id: int = 42) -> MagicMock:
    response = MagicMock()
    response.json.return_value = {
        "ok": True,
        "result": {"message_id": message_id},
    }
    http_client = MagicMock()
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=False)
    http_client.post = AsyncMock(return_value=response)
    return http_client


def _mock_telegram_failure(description: str = "Bad Request") -> MagicMock:
    response = MagicMock()
    response.json.return_value = {"ok": False, "description": description}
    http_client = MagicMock()
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=False)
    http_client.post = AsyncMock(return_value=response)
    return http_client


def test_alert_requires_auth():
    r = client.post("/alert", json=VALID_PAYLOAD)
    assert r.status_code == 401


def test_alert_rejects_wrong_bearer():
    r = client.post(
        "/alert",
        json=VALID_PAYLOAD,
        headers={"Authorization": "Bearer wrongtoken"},
    )
    assert r.status_code == 401


def test_alert_valid_payload_calls_telegram():
    mock_http = _mock_telegram_success(message_id=99)
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http):
        r = client.post("/alert", json=VALID_PAYLOAD, headers=AUTH)

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["telegram_message_id"] == 99
    mock_http.post.assert_called_once()
    call_args = mock_http.post.call_args
    sent_text = call_args[1]["json"]["text"]
    assert "sherlock-hq" in sent_text
    assert "DOWN" in sent_text
    assert "🔴" in sent_text


def test_alert_telegram_failure_returns_200_with_error():
    """Watcher should not retry — always return HTTP 200."""
    mock_http = _mock_telegram_failure("Chat not found")
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http):
        r = client.post("/alert", json=VALID_PAYLOAD, headers=AUTH)

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "Chat not found" in body["error"]


def test_alert_missing_service_returns_422():
    r = client.post(
        "/alert",
        json={"transition": "ok->down"},
        headers=AUTH,
    )
    assert r.status_code == 422


def test_alert_missing_transition_returns_422():
    r = client.post(
        "/alert",
        json={"service": "sherlock-hq"},
        headers=AUTH,
    )
    assert r.status_code == 422


def test_alert_log_tail_truncated_to_20():
    """log_tail longer than 20 lines should be truncated."""
    payload = {**VALID_PAYLOAD, "log_tail": [f"line {i}" for i in range(50)]}
    mock_http = _mock_telegram_success()
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http):
        r = client.post("/alert", json=payload, headers=AUTH)

    assert r.status_code == 200
    sent_text = mock_http.post.call_args[1]["json"]["text"]
    # Only last 20 lines should appear
    assert "line 49" in sent_text
    assert "line 0" not in sent_text


def test_alert_formats_transition_message():
    payload = {
        "service": "things-mcp",
        "transition": "down->ok",
        "detail": "Recovered",
    }
    mock_http = _mock_telegram_success()
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http):
        r = client.post("/alert", json=payload, headers=AUTH)

    assert r.status_code == 200
    sent_text = mock_http.post.call_args[1]["json"]["text"]
    assert "🟢" in sent_text
    assert "OK" in sent_text
    assert "things-mcp" in sent_text
    assert "Recovered" in sent_text
