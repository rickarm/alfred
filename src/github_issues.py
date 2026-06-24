"""Auto-file GitHub issues for true outages/bugs detected via the /alert endpoint.

The service watcher (``scripts/services-check.sh`` / system-monitor) POSTs state
transitions to ``/alert``. When a transition represents a high-confidence true
outage, this module files a GitHub issue on the appropriate repo so the follow-up
work doesn't depend on Rick manually noticing the Telegram alert.

Guardrails (see issue #15):
- Only file for high-confidence outages — a transition whose *destination* state is
  ``down``. Recoveries (``-> ok``) and the ambiguous/transient ``degraded`` state are
  intentionally excluded so transient/informational events don't create noise.
- Deduplicate against existing open issues using a stable per-service marker embedded
  in the issue body, so an ongoing outage never spawns repeated issues.
- Opt-in: nothing is filed unless ``GITHUB_AUTOFILE_ENABLED`` is true and a token is set.
- Best-effort: every entry point swallows errors so issue filing can never block or
  break the Telegram alert path.
"""

import logging
from datetime import datetime, timezone

import httpx

from .config import settings

logger = logging.getLogger(__name__)

# Destination states we treat as high-confidence true outages worth filing.
# Recoveries (-> ok) and transient/degraded transitions are deliberately excluded.
FILEABLE_STATES = frozenset({"down"})

# Marker embedded in each auto-filed issue body, used for per-service deduplication.
_MARKER_PREFIX = "alfred-incident"


def _destination_state(transition: str) -> str:
    """Return the lowercased 'to' side of an 'a->b' transition string."""
    _, _, to_state = transition.partition("->")
    return to_state.strip().lower()


def should_file(transition: str) -> bool:
    """True only for high-confidence outage transitions (destination == down)."""
    return _destination_state(transition) in FILEABLE_STATES


def _parse_repo_map(raw: str) -> dict[str, str]:
    """Parse 'service=owner/repo,other=owner/repo2' into a dict."""
    mapping: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" not in pair:
            continue
        svc, _, repo = pair.partition("=")
        svc, repo = svc.strip(), repo.strip()
        if svc and repo:
            mapping[svc] = repo
    return mapping


def repo_for_service(service: str) -> str:
    """Resolve the most appropriate 'owner/repo' for a service, or '' if none."""
    return _parse_repo_map(settings.github_service_repos).get(
        service, settings.github_default_repo
    )


def _labels() -> list[str]:
    return [label.strip() for label in settings.github_issue_labels.split(",") if label.strip()]


def _marker(service: str) -> str:
    """Stable HTML-comment fingerprint used to dedup issues per service."""
    return f"<!-- {_MARKER_PREFIX}:{service} -->"


def _severity(transition: str) -> str:
    to_state = _destination_state(transition)
    if to_state == "down":
        return "High — service is down (outage)"
    if to_state == "degraded":
        return "Medium — service degraded"
    return "Unknown"


def build_issue(payload) -> tuple[str, str, list[str]]:
    """Build (title, body, labels) for an alert payload.

    The body is rendered Markdown carrying everything a developer needs to act:
    summary, timestamp + detection source, affected component/repo, evidence/log
    excerpts, severity, suspected cause, and a recommended next step.
    """
    service = payload.service
    transition = payload.transition
    to_state = _destination_state(transition)
    timestamp = datetime.now(timezone.utc).isoformat()
    repo = repo_for_service(service)

    title = f"[outage] {service} is {to_state}"

    if payload.log_tail:
        excerpt = "\n".join(["```", *payload.log_tail[-20:], "```"])
        evidence = f"{payload.detail}\n\n{excerpt}" if payload.detail else excerpt
    elif payload.detail:
        evidence = payload.detail
    else:
        evidence = "_No additional evidence captured._"

    log_file = f"`{payload.log_file}`" if payload.log_file else "_not provided_"
    suspected = payload.detail or "Unknown — see evidence above."

    body = f"""{_marker(service)}
**Summary:** `{service}` transitioned `{transition}`, detected as a true outage.

| Field | Value |
| --- | --- |
| Detected at | {timestamp} |
| Detection source | service watcher → Alfred `/alert` |
| Affected component | `{service}` |
| Repository | `{repo}` |
| Severity | {_severity(transition)} |
| Log file | {log_file} |

### Evidence / symptoms
{evidence}

### Suspected cause
{suspected}

### Recommended next step
Inspect the log file above, confirm the outage, and restart the service \
(`/restart {service}`) if appropriate. Close this issue once the service recovers \
and the root cause is understood.

---
_Filed automatically by Alfred. Deduplicated per service while this issue stays open._
"""
    return title, body, _labels()


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def find_existing_issue(repo: str, service: str) -> dict | None:
    """Return an open auto-filed issue for this service, or None.

    Scans open issues (pull requests excluded) for the per-service marker. This is
    what prevents an ongoing outage from spawning repeated duplicate issues.
    """
    marker = _marker(service)
    url = f"{settings.github_api_url}/repos/{repo}/issues"
    params = {"state": "open", "per_page": 100}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers=_headers(), params=params)
    r.raise_for_status()
    for issue in r.json():
        if "pull_request" in issue:  # /issues also returns PRs; skip them
            continue
        if marker in (issue.get("body") or ""):
            return issue
    return None


async def create_issue(repo: str, title: str, body: str, labels: list[str]) -> dict:
    url = f"{settings.github_api_url}/repos/{repo}/issues"
    json_body: dict = {"title": title, "body": body}
    if labels:
        json_body["labels"] = labels
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, headers=_headers(), json=json_body)
    r.raise_for_status()
    return r.json()


async def maybe_file_issue(payload) -> dict:
    """Best-effort: file a GitHub issue for a true outage. Never raises.

    Returns a small status dict describing what happened (filed / skipped / why),
    suitable for attaching to the /alert response meta.
    """
    if not settings.github_autofile_enabled:
        return {"filed": False, "reason": "disabled"}
    if not settings.github_token:
        return {"filed": False, "reason": "no-token"}
    if not should_file(payload.transition):
        return {"filed": False, "reason": "not-fileable-transition"}

    repo = repo_for_service(payload.service)
    if not repo:
        return {"filed": False, "reason": "no-repo"}

    try:
        existing = await find_existing_issue(repo, payload.service)
        if existing:
            logger.info(
                "Skipping duplicate incident issue for %s: %s",
                payload.service,
                existing.get("html_url"),
            )
            return {
                "filed": False,
                "reason": "duplicate",
                "issue_url": existing.get("html_url"),
                "issue_number": existing.get("number"),
            }

        title, body, labels = build_issue(payload)
        issue = await create_issue(repo, title, body, labels)
        logger.info("Filed incident issue for %s: %s", payload.service, issue.get("html_url"))
        return {
            "filed": True,
            "issue_url": issue.get("html_url"),
            "issue_number": issue.get("number"),
        }
    except Exception as e:
        logger.exception("Failed to auto-file incident issue for %s", payload.service)
        return {"filed": False, "reason": "error", "error": str(e)}
