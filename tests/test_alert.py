"""Tests for POST /alert endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.config import settings
from src.main import app
from src.routes.alert import _alert_filter

client = TestClient(app)
AUTH = {"Authorization": f"Bearer {settings.things_agent_api_key}"}

# Use a non-silent, non-grouped service as the default test service.
VALID_PAYLOAD = {
    "service": "things-mcp",
    "transition": "ok->down",
    "detail": "HTTP 000 (timeout after 5s)",
    "log_tail": ["line1", "line2"],
}


@pytest.fixture(autouse=True)
def reset_alert_filter():
    """Clear in-memory cooldown state between tests."""
    _alert_filter._reset()
    yield
    _alert_filter._reset()


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


# ---------------------------------------------------------------------------
# Auth tests (service is sherlock-hq here but auth check is pre-filter)
# ---------------------------------------------------------------------------

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
        json={"service": "things-mcp"},
        headers=AUTH,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Core routing tests
# ---------------------------------------------------------------------------

def test_alert_valid_payload_calls_telegram():
    mock_http = _mock_telegram_success(message_id=99)
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http):
        r = client.post("/alert", json=VALID_PAYLOAD, headers=AUTH)

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["telegram_message_id"] == 99
    mock_http.post.assert_called_once()
    sent_text = mock_http.post.call_args[1]["json"]["text"]
    assert "things-mcp" in sent_text
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


def test_alert_includes_log_path_when_down():
    """down/degraded alerts show the log-file path instead of inline log lines."""
    payload = {
        **VALID_PAYLOAD,
        "log_file": "/var/log/things-mcp/service.log",
        "log_tail": [f"line {i}" for i in range(50)],
    }
    mock_http = _mock_telegram_success()
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http):
        r = client.post("/alert", json=payload, headers=AUTH)

    assert r.status_code == 200
    sent_text = mock_http.post.call_args[1]["json"]["text"]
    assert "/var/log/things-mcp/service.log" in sent_text
    assert "line 49" not in sent_text
    assert len(sent_text.split("\n")) <= 3


def test_alert_recovery_has_no_log_path():
    """A down->ok recovery has no problem, so no log-file line."""
    payload = {
        "service": "things-mcp",
        "transition": "down->ok",
        "detail": "Recovered",
        "log_file": "/var/log/things-mcp.log",
    }
    mock_http = _mock_telegram_success()
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http):
        r = client.post("/alert", json=payload, headers=AUTH)

    assert r.status_code == 200
    sent_text = mock_http.post.call_args[1]["json"]["text"]
    assert "📄" not in sent_text
    assert len(sent_text.split("\n")) <= 3


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


# ---------------------------------------------------------------------------
# Silent service tests
# ---------------------------------------------------------------------------

def test_silent_service_is_suppressed():
    """Alerts for silenced services return ok=True, suppressed=True with no Telegram call."""
    for service in ("checkout-server", "things-export", "repo-sync", "sherlock-hq"):
        _alert_filter._reset()
        mock_http = _mock_telegram_success()
        with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http):
            r = client.post(
                "/alert",
                json={"service": service, "transition": "ok->down", "detail": "test"},
                headers=AUTH,
            )
        assert r.status_code == 200, f"expected 200 for {service}"
        body = r.json()
        assert body.get("ok") is True
        assert body.get("suppressed") is True
        mock_http.post.assert_not_called()


# ---------------------------------------------------------------------------
# Cooldown / severity tests
# ---------------------------------------------------------------------------

def test_degraded_cooldown_suppresses_repeat():
    """Second →degraded alert for the same service within 30 min is suppressed."""
    payload = {"service": "alfred", "transition": "ok->degraded", "detail": "slow"}
    mock_http = _mock_telegram_success()
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http):
        r1 = client.post("/alert", json=payload, headers=AUTH)
    assert r1.json()["ok"] is True
    assert "suppressed" not in r1.json()

    mock_http2 = _mock_telegram_success()
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http2):
        r2 = client.post("/alert", json=payload, headers=AUTH)
    assert r2.status_code == 200
    assert r2.json().get("suppressed") is True
    mock_http2.post.assert_not_called()


def test_down_after_degraded_fires_despite_cooldown():
    """→down always fires for standalone services even while degraded cooldown is active."""
    mock_http = _mock_telegram_success()
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http):
        client.post(
            "/alert",
            json={"service": "alfred", "transition": "ok->degraded", "detail": "slow"},
            headers=AUTH,
        )

    mock_http2 = _mock_telegram_success(message_id=2)
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http2):
        r = client.post(
            "/alert",
            json={"service": "alfred", "transition": "degraded->down", "detail": "gone"},
            headers=AUTH,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "suppressed" not in body
    mock_http2.post.assert_called_once()


def test_recovery_from_degraded_is_suppressed():
    """→ok is suppressed when prior tracked state was degraded (not down)."""
    mock_http = _mock_telegram_success()
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http):
        client.post(
            "/alert",
            json={"service": "alfred", "transition": "ok->degraded", "detail": "blip"},
            headers=AUTH,
        )

    mock_http2 = _mock_telegram_success()
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http2):
        r = client.post(
            "/alert",
            json={"service": "alfred", "transition": "degraded->ok", "detail": "recovered"},
            headers=AUTH,
        )
    assert r.status_code == 200
    assert r.json().get("suppressed") is True
    mock_http2.post.assert_not_called()


def test_recovery_from_down_fires():
    """→ok fires when prior tracked state was down."""
    mock_http = _mock_telegram_success()
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http):
        client.post(
            "/alert",
            json={"service": "alfred", "transition": "ok->down", "detail": "gone"},
            headers=AUTH,
        )

    mock_http2 = _mock_telegram_success(message_id=2)
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http2):
        r = client.post(
            "/alert",
            json={"service": "alfred", "transition": "down->ok", "detail": "back"},
            headers=AUTH,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "suppressed" not in body
    mock_http2.post.assert_called_once()


# ---------------------------------------------------------------------------
# OpenClaw group consolidation tests
# ---------------------------------------------------------------------------

def test_openclaw_group_first_alert_fires():
    """First openclaw-family alert fires and uses the group name 'openclaw'."""
    mock_http = _mock_telegram_success()
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http):
        r = client.post(
            "/alert",
            json={"service": "openclaw-agent", "transition": "ok->down", "detail": "not loaded"},
            headers=AUTH,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "suppressed" not in body
    sent_text = mock_http.post.call_args[1]["json"]["text"]
    # Display name should be the group key, not the individual member.
    assert "openclaw" in sent_text
    assert "openclaw-agent" not in sent_text


def test_openclaw_group_subsequent_alerts_suppressed():
    """After the first openclaw-family alert, subsequent members are suppressed."""
    # First: openclaw-agent fires
    mock_http1 = _mock_telegram_success()
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http1):
        client.post(
            "/alert",
            json={"service": "openclaw-agent", "transition": "ok->down", "detail": "not loaded"},
            headers=AUTH,
        )

    # Second: openclaw → degraded is suppressed (group cooldown active, state didn't worsen)
    mock_http2 = _mock_telegram_success()
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http2):
        r2 = client.post(
            "/alert",
            json={"service": "openclaw", "transition": "ok->degraded", "detail": "blip"},
            headers=AUTH,
        )
    assert r2.json().get("suppressed") is True
    mock_http2.post.assert_not_called()

    # Third: openclaw-functional-health → down is suppressed (group already in "down" state)
    mock_http3 = _mock_telegram_success()
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http3):
        r3 = client.post(
            "/alert",
            json={
                "service": "openclaw-functional-health",
                "transition": "ok->down",
                "detail": "STATUS=down",
            },
            headers=AUTH,
        )
    assert r3.json().get("suppressed") is True
    mock_http3.post.assert_not_called()


def _post(service: str, transition: str) -> dict:
    """Helper: POST one alert with a fresh telegram mock; return (json, mock)."""
    mock_http = _mock_telegram_success()
    with patch("src.routes.alert.httpx.AsyncClient", return_value=mock_http):
        r = client.post(
            "/alert",
            json={"service": service, "transition": transition, "detail": "x"},
            headers=AUTH,
        )
    return r.json(), mock_http


def test_grouped_recovery_held_until_all_members_healthy():
    """A grouped recovery must not fire while a sibling member is still down.

    Two openclaw members go down (one alert), then recover one at a time. The
    first member's recovery is held back; only the recovery that clears the last
    unhealthy member fires the single 'all clear'.
    """
    # Member A down → fires the one group alert.
    body, http = _post("openclaw-agent", "ok->down")
    assert "suppressed" not in body
    http.post.assert_called_once()

    # Member B down → suppressed (group already alerted).
    body, http = _post("openclaw-functional-health", "ok->down")
    assert body.get("suppressed") is True
    http.post.assert_not_called()

    # Member A recovers, but B is still down → recovery held, no false all-clear.
    body, http = _post("openclaw-agent", "down->ok")
    assert body.get("suppressed") is True
    http.post.assert_not_called()

    # Member B recovers → roster empties → single recovery fires.
    body, http = _post("openclaw-functional-health", "down->ok")
    assert "suppressed" not in body
    http.post.assert_called_once()
    sent_text = http.post.call_args[1]["json"]["text"]
    assert "openclaw" in sent_text
    assert "🟢" in sent_text


def test_grouped_degraded_only_recovery_is_routine():
    """A group that only ever degraded (never down) recovering is treated as routine."""
    # Degraded → fires the warning.
    body, _ = _post("openclaw", "ok->degraded")
    assert "suppressed" not in body

    # Recovery from degraded-only → suppressed (matches 'recover only from down').
    body, http = _post("openclaw", "degraded->ok")
    assert body.get("suppressed") is True
    http.post.assert_not_called()
