"""Tests for auto-filing GitHub issues on true outages (src/github_issues.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

from src import github_issues
from src.routes.alert import AlertPayload


def _payload(**overrides) -> AlertPayload:
    base = {
        "service": "sherlock-hq",
        "transition": "ok->down",
        "detail": "HTTP 000 (timeout after 5s)",
        "log_file": "/var/log/sherlock-hq/service.log",
        "log_tail": ["boom line 1", "boom line 2"],
    }
    base.update(overrides)
    return AlertPayload(**base)


def _mock_client(*, get_json=None, post_json=None, get_status=200, post_status=201) -> MagicMock:
    """Build a mock httpx.AsyncClient usable as an async context manager."""
    get_resp = MagicMock()
    get_resp.json.return_value = get_json if get_json is not None else []
    get_resp.status_code = get_status
    get_resp.raise_for_status = MagicMock()

    post_resp = MagicMock()
    post_resp.json.return_value = post_json if post_json is not None else {}
    post_resp.status_code = post_status
    post_resp.raise_for_status = MagicMock()

    http_client = MagicMock()
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=False)
    http_client.get = AsyncMock(return_value=get_resp)
    http_client.post = AsyncMock(return_value=post_resp)
    return http_client


# --- Pure triage / helpers -------------------------------------------------


def test_should_file_only_for_down():
    assert github_issues.should_file("ok->down") is True
    assert github_issues.should_file("degraded->down") is True
    # Recoveries and transient/degraded transitions are excluded.
    assert github_issues.should_file("down->ok") is False
    assert github_issues.should_file("ok->degraded") is False
    assert github_issues.should_file("degraded->ok") is False


def test_repo_for_service_mapping_and_fallback():
    with patch.object(github_issues.settings, "github_service_repos", "things-mcp=rickarm/things"):
        with patch.object(github_issues.settings, "github_default_repo", "rickarm/alfred"):
            assert github_issues.repo_for_service("things-mcp") == "rickarm/things"
            assert github_issues.repo_for_service("sherlock-hq") == "rickarm/alfred"


def test_build_issue_includes_required_context():
    title, body, labels = github_issues.build_issue(_payload())
    assert "sherlock-hq" in title
    assert "down" in title
    # Required content from the issue spec.
    assert "Summary" in body
    assert "Detected at" in body
    assert "Detection source" in body
    assert "Affected component" in body
    assert "Severity" in body
    assert "Recommended next step" in body
    # Evidence and log excerpt surfaced.
    assert "HTTP 000" in body
    assert "boom line 2" in body
    assert "/var/log/sherlock-hq/service.log" in body
    # Stable dedup marker present.
    assert github_issues._marker("sherlock-hq") in body
    assert labels == ["bug", "claude"]


# --- maybe_file_issue guardrails ------------------------------------------


async def test_disabled_by_default():
    result = await github_issues.maybe_file_issue(_payload())
    assert result == {"filed": False, "reason": "disabled"}


async def test_skips_when_no_token():
    with patch.object(github_issues.settings, "github_autofile_enabled", True):
        with patch.object(github_issues.settings, "github_token", ""):
            result = await github_issues.maybe_file_issue(_payload())
    assert result["reason"] == "no-token"


async def test_skips_non_fileable_transition():
    with patch.object(github_issues.settings, "github_autofile_enabled", True):
        with patch.object(github_issues.settings, "github_token", "tok"):
            result = await github_issues.maybe_file_issue(_payload(transition="ok->degraded"))
    assert result["reason"] == "not-fileable-transition"


async def test_skips_when_no_repo():
    with patch.object(github_issues.settings, "github_autofile_enabled", True):
        with patch.object(github_issues.settings, "github_token", "tok"):
            with patch.object(github_issues.settings, "github_default_repo", ""):
                with patch.object(github_issues.settings, "github_service_repos", ""):
                    result = await github_issues.maybe_file_issue(_payload())
    assert result["reason"] == "no-repo"


async def test_files_issue_when_no_duplicate():
    mock_http = _mock_client(
        get_json=[],
        post_json={"html_url": "https://github.com/rickarm/alfred/issues/42", "number": 42},
    )
    with patch.object(github_issues.settings, "github_autofile_enabled", True):
        with patch.object(github_issues.settings, "github_token", "tok"):
            with patch.object(github_issues.settings, "github_default_repo", "rickarm/alfred"):
                with patch("src.github_issues.httpx.AsyncClient", return_value=mock_http):
                    result = await github_issues.maybe_file_issue(_payload())

    assert result["filed"] is True
    assert result["issue_number"] == 42
    mock_http.post.assert_called_once()
    sent = mock_http.post.call_args[1]["json"]
    assert sent["labels"] == ["bug", "claude"]
    assert "sherlock-hq" in sent["title"]


async def test_dedups_against_existing_open_issue():
    marker = github_issues._marker("sherlock-hq")
    existing = [
        {"number": 7, "html_url": "https://github.com/rickarm/alfred/issues/7", "body": marker},
    ]
    mock_http = _mock_client(get_json=existing)
    with patch.object(github_issues.settings, "github_autofile_enabled", True):
        with patch.object(github_issues.settings, "github_token", "tok"):
            with patch.object(github_issues.settings, "github_default_repo", "rickarm/alfred"):
                with patch("src.github_issues.httpx.AsyncClient", return_value=mock_http):
                    result = await github_issues.maybe_file_issue(_payload())

    assert result["filed"] is False
    assert result["reason"] == "duplicate"
    assert result["issue_number"] == 7
    mock_http.post.assert_not_called()


async def test_pull_requests_are_ignored_during_dedup():
    marker = github_issues._marker("sherlock-hq")
    # A PR carrying the marker must NOT be treated as a duplicate issue.
    listing = [
        {"number": 9, "html_url": "x", "body": marker, "pull_request": {"url": "..."}},
    ]
    mock_http = _mock_client(
        get_json=listing,
        post_json={"html_url": "https://github.com/rickarm/alfred/issues/43", "number": 43},
    )
    with patch.object(github_issues.settings, "github_autofile_enabled", True):
        with patch.object(github_issues.settings, "github_token", "tok"):
            with patch.object(github_issues.settings, "github_default_repo", "rickarm/alfred"):
                with patch("src.github_issues.httpx.AsyncClient", return_value=mock_http):
                    result = await github_issues.maybe_file_issue(_payload())

    assert result["filed"] is True
    assert result["issue_number"] == 43


async def test_errors_are_swallowed():
    mock_http = _mock_client()
    mock_http.get = AsyncMock(side_effect=RuntimeError("network down"))
    with patch.object(github_issues.settings, "github_autofile_enabled", True):
        with patch.object(github_issues.settings, "github_token", "tok"):
            with patch.object(github_issues.settings, "github_default_repo", "rickarm/alfred"):
                with patch("src.github_issues.httpx.AsyncClient", return_value=mock_http):
                    result = await github_issues.maybe_file_issue(_payload())

    assert result["filed"] is False
    assert result["reason"] == "error"
    assert "network down" in result["error"]
