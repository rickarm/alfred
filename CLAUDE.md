# Alfred: Personal Assistant Bot

Telegram bot + FastAPI gateway integrating Claude and Things 3 via MCP. Runs on mac mini, port 8200.

## Development Workflow

See `KB-Development-Workflow.md` in the Knowledge Base for the full workflow. Summary:

1. Bugs and features are tracked as **GitHub Issues**
2. Claude works on a **feature branch** (worktrees for isolation in local sessions)
3. Claude pushes the branch and opens a **Pull Request**
4. Rick reviews and merges the PR
5. Adding the `claude` label to an issue triggers Claude via GitHub Actions

## Commands

```bash
make setup     # Create venv and install deps (uv sync)
make dev       # uvicorn with auto-reload on port 8200
make test      # Run pytest
make health    # curl health endpoint
make start     # Load launchd plist (production)
make stop      # Unload launchd plist
make restart   # stop + start
make logs      # Tail stdout log
make errors    # Tail stderr log
```

## Architecture

```
Telegram → FastAPI (port 8200) → Claude API → MCP Client → things-mcp (port 8100) → Things 3
scripts/services-check.sh → POST /alert → Telegram (Rick's chat)
/services /status /restart /logs → Sherlock-HQ (port 8300) → Telegram
```

```
src/
  main.py           # FastAPI app, lifespan, mounts routes
  bot.py            # Telegram handler setup (wires the skill registry + agent)
  agent.py          # Claude agent loop: run(message, tools, execute_tool)
  prompts.py        # Agent system prompt
  tg.py             # Shared Telegram helpers: guard() auth, send()
  routes/
    things.py       # Things 3 REST API endpoints (structured CRUD)
    agent.py        # POST /api/v1/message (natural-language → Things edits)
    alert.py        # POST /alert (service watcher push)
  commands/
    services.py     # /services /status /restart /logs handlers
  skills/
    registry.py     # SkillRegistry: aggregates tools + handlers
    base.py         # Skill ABC
    things/         # ThingsSkill: Claude tools + slash commands + executor
    checkout/       # CheckoutSkill: end-of-day journal conversation
  config.py         # Env-based settings (pydantic-settings)
tests/
  test_routes.py         # Things REST route tests
  test_agent_endpoint.py # POST /api/v1/message tests
  test_services_commands.py  # Service command handler tests
  test_alert.py          # POST /alert endpoint tests
```

## Natural-language Things editing

Free-text drives Things 3 edits through the Claude agent loop (`agent.run`), using
the tools + executor registered by `ThingsSkill` (`skills/things/`). Edits execute
immediately and the reply describes what changed (no confirmation step). This is the
fallback for when the native Things app / MCP / AppleScript aren't reachable (iPhone,
iPad, agent chat in a VM/container, etc.).

Two entry points share the same agent path:
- **Telegram:** send a plain message (e.g. "remind me to call the dentist tomorrow",
  "mark the buy-milk task done"). Handled by `bot.handle_message`. Slash commands
  (`/today`, `/inbox`, …) still work for reads.
- **HTTP (programmatic):** `POST /api/v1/message` with `{"message": "..."}` and a
  Bearer token. Returns `{"ok": true, "data": {"reply": "..."}, "meta": {...}}`.
  Structured endpoints (`POST /todos`, `PATCH /todos/{id}`, …) remain available for
  precise edits.

**Reachability:** Alfred binds `0.0.0.0`, so a remote agent on Rick's tailnet reaches
it via MagicDNS at `http://mac-mini:8200/api/v1/message` (FQDN
`mac-mini.<tailnet>.ts.net:8200` if the short name isn't in the caller's DNS search
domain). Internal hops stay loopback (`127.0.0.1`) since the bot + API are co-located.
Telegram needs no inbound exposure — the bot polls outbound.

**Auth:** `TELEGRAM_ALLOWED_USER_IDS` (comma-separated user IDs) gates the bot via
`tg.guard()`; empty = allow all. The HTTP endpoint uses the same Bearer auth as the
rest of `/api/v1`.

## Telegram commands (service monitoring)

All service commands only respond to `RICK_CHAT_ID`. Commands call Sherlock-HQ (`http://127.0.0.1:8300` by default).

- `/services` — List all services with status icons and counts
- `/status <name>` — Detail for one service + last 10 log lines (404 reply if unknown)
- `/restart <name>` — Restart a service group; replies with per-member exit codes
- `/logs <name> [N]` — Last N log lines (default 50, max 200; 404 reply if unknown)

## Environment

`.env` file (copy from `.env.example`):
- `ALFRED_API_KEY` — Bearer token for API auth (all endpoints except /health)
- `THINGS_MCP_URL` — MCP server URL (default: http://127.0.0.1:8100)
- `TELEGRAM_BOT_TOKEN` — Telegram Bot API token
- `ANTHROPIC_API_KEY` — Claude API key
- `CLAUDE_MODEL` — Model ID (default: claude-sonnet-4-6)
- `SHERLOCK_HQ_URL` — Sherlock-HQ base URL (default: http://127.0.0.1:8300)
- `SHERLOCK_DASHBOARD_TOKEN` — Bearer token for Sherlock-HQ API calls (required)
- `RICK_CHAT_ID` — Telegram chat ID for alerts and command responses (required)
- `ALFRED_BASE_URL` — Alfred's own REST gateway, used by the agent executor (default: http://127.0.0.1:8200/api/v1; keep loopback)
- `TELEGRAM_ALLOWED_USER_IDS` — comma-separated Telegram user IDs allowed to use the bot (empty = allow all)

## Gotchas

- MCP server (things-mcp) must be running on port 8100 as a separate process
- API requires Bearer token auth on all endpoints except `/health`
- Uses UV package manager, not pip
- launchd plist is `com.rickarmbrust.things-agent` (not `alfred`)
- Port 8200 chosen to avoid conflict with sherlock-hq (8300) and things-mcp (8100)
