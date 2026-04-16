"""Tests for Telegram service command handlers (Sherlock-HQ calls mocked)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.commands.services import cmd_logs, cmd_restart, cmd_services, cmd_status

RICK_ID = 12345
OTHER_ID = 99999

MOCK_SERVICES = [
    {"name": "sherlock-hq", "status": "ok", "detail": "HTTP 200 in 42ms"},
    {"name": "alfred", "status": "ok", "detail": "HTTP 200 in 38ms"},
    {"name": "things-export", "status": "down", "detail": "no snapshot files"},
    {"name": "things-mcp-restart", "status": "degraded", "detail": "no marker"},
]


def _make_update(chat_id: int) -> MagicMock:
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.reply_text = AsyncMock()
    return update


def _make_context(*args: str) -> MagicMock:
    ctx = MagicMock()
    ctx.args = list(args)
    return ctx


def _mock_client(status_code: int = 200, json_data=None):
    """Return a mock httpx.AsyncClient context manager."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data if json_data is not None else []
    response.raise_for_status = MagicMock()

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    return client


# ---------------------------------------------------------------------------
# /services
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_services_formats_table():
    update = _make_update(RICK_ID)
    ctx = _make_context()
    mock = _mock_client(json_data=MOCK_SERVICES)

    with patch("src.commands.services.settings") as mock_settings, patch(
        "src.commands.services.httpx.AsyncClient", return_value=mock
    ):
        mock_settings.rick_chat_id = RICK_ID
        mock_settings.sherlock_hq_url = "http://localhost:8300"
        mock_settings.sherlock_dashboard_token = "tok"
        await cmd_services(update, ctx)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "🟢" in text
    assert "🔴" in text
    assert "🟡" in text
    assert "sherlock-hq" in text
    assert "2 ok" in text
    assert "1 degraded" in text
    assert "1 down" in text


@pytest.mark.asyncio
async def test_services_rejects_unauthorized():
    update = _make_update(OTHER_ID)
    ctx = _make_context()

    with patch("src.commands.services.settings") as mock_settings:
        mock_settings.rick_chat_id = RICK_ID
        await cmd_services(update, ctx)

    update.message.reply_text.assert_not_called()


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_unknown_service():
    update = _make_update(RICK_ID)
    ctx = _make_context("unknown-svc")

    not_found = MagicMock()
    not_found.status_code = 404
    not_found.json.return_value = {}

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=not_found)

    with patch("src.commands.services.settings") as mock_settings, patch(
        "src.commands.services.httpx.AsyncClient", return_value=client
    ):
        mock_settings.rick_chat_id = RICK_ID
        mock_settings.sherlock_hq_url = "http://localhost:8300"
        mock_settings.sherlock_dashboard_token = "tok"
        await cmd_status(update, ctx)

    update.message.reply_text.assert_called_once_with("Unknown service: unknown-svc")


@pytest.mark.asyncio
async def test_status_known_service():
    update = _make_update(RICK_ID)
    ctx = _make_context("sherlock-hq")

    svc_response = MagicMock()
    svc_response.status_code = 200
    svc_response.json.return_value = {
        "name": "sherlock-hq",
        "status": "ok",
        "detail": "HTTP 200",
        "last_ok": "2026-04-16T23:00:00Z",
        "last_fail": "never",
        "consecutive_failures": 0,
    }
    svc_response.raise_for_status = MagicMock()

    log_response = MagicMock()
    log_response.status_code = 200
    log_response.json.return_value = ["line1", "line2"]

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=[svc_response, log_response])

    with patch("src.commands.services.settings") as mock_settings, patch(
        "src.commands.services.httpx.AsyncClient", return_value=client
    ):
        mock_settings.rick_chat_id = RICK_ID
        mock_settings.sherlock_hq_url = "http://localhost:8300"
        mock_settings.sherlock_dashboard_token = "tok"
        await cmd_status(update, ctx)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "sherlock-hq" in text
    assert "🟢" in text


@pytest.mark.asyncio
async def test_status_rejects_unauthorized():
    update = _make_update(OTHER_ID)
    with patch("src.commands.services.settings") as mock_settings:
        mock_settings.rick_chat_id = RICK_ID
        await cmd_status(update, _make_context("svc"))
    update.message.reply_text.assert_not_called()


# ---------------------------------------------------------------------------
# /restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restart_includes_exit_codes():
    update = _make_update(RICK_ID)
    ctx = _make_context("things-mcp")

    restart_data = [
        {"name": "things-mcp", "exit_code": 0},
        {"name": "things-bot", "exit_code": 0},
    ]
    mock = _mock_client(json_data=restart_data)

    with patch("src.commands.services.settings") as mock_settings, patch(
        "src.commands.services.httpx.AsyncClient", return_value=mock
    ):
        mock_settings.rick_chat_id = RICK_ID
        mock_settings.sherlock_hq_url = "http://localhost:8300"
        mock_settings.sherlock_dashboard_token = "tok"
        await cmd_restart(update, ctx)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "things-mcp (exit 0)" in text
    assert "things-bot (exit 0)" in text


@pytest.mark.asyncio
async def test_restart_rejects_unauthorized():
    update = _make_update(OTHER_ID)
    with patch("src.commands.services.settings") as mock_settings:
        mock_settings.rick_chat_id = RICK_ID
        await cmd_restart(update, _make_context("svc"))
    update.message.reply_text.assert_not_called()


# ---------------------------------------------------------------------------
# /logs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logs_defaults_to_50():
    update = _make_update(RICK_ID)
    ctx = _make_context("sherlock-hq")  # no N arg

    mock = _mock_client(json_data=["log line"] * 50)

    with patch("src.commands.services.settings") as mock_settings, patch(
        "src.commands.services.httpx.AsyncClient", return_value=mock
    ):
        mock_settings.rick_chat_id = RICK_ID
        mock_settings.sherlock_hq_url = "http://localhost:8300"
        mock_settings.sherlock_dashboard_token = "tok"
        await cmd_logs(update, ctx)

    call_kwargs = mock.get.call_args[1]
    assert call_kwargs["params"]["tail"] == "50"


@pytest.mark.asyncio
async def test_logs_caps_at_200():
    update = _make_update(RICK_ID)
    ctx = _make_context("sherlock-hq", "999")  # request 999, should cap at 200

    mock = _mock_client(json_data=["log line"] * 200)

    with patch("src.commands.services.settings") as mock_settings, patch(
        "src.commands.services.httpx.AsyncClient", return_value=mock
    ):
        mock_settings.rick_chat_id = RICK_ID
        mock_settings.sherlock_hq_url = "http://localhost:8300"
        mock_settings.sherlock_dashboard_token = "tok"
        await cmd_logs(update, ctx)

    call_kwargs = mock.get.call_args[1]
    assert call_kwargs["params"]["tail"] == "200"


@pytest.mark.asyncio
async def test_logs_unknown_service():
    update = _make_update(RICK_ID)
    ctx = _make_context("unknown-svc")

    not_found = MagicMock()
    not_found.status_code = 404
    not_found.json.return_value = {}

    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=not_found)

    with patch("src.commands.services.settings") as mock_settings, patch(
        "src.commands.services.httpx.AsyncClient", return_value=client
    ):
        mock_settings.rick_chat_id = RICK_ID
        mock_settings.sherlock_hq_url = "http://localhost:8300"
        mock_settings.sherlock_dashboard_token = "tok"
        await cmd_logs(update, ctx)

    update.message.reply_text.assert_called_once_with("Unknown service: unknown-svc")


@pytest.mark.asyncio
async def test_logs_rejects_unauthorized():
    update = _make_update(OTHER_ID)
    with patch("src.commands.services.settings") as mock_settings:
        mock_settings.rick_chat_id = RICK_ID
        await cmd_logs(update, _make_context("svc"))
    update.message.reply_text.assert_not_called()
