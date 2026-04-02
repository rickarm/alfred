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
```

```
src/
  main.py      # FastAPI app, lifespan, mounts routes
  bot.py       # Telegram handler setup
  routes.py    # REST API endpoints
  config.py    # Env-based settings (pydantic-settings)
tests/
  test_routes.py  # REST route tests
```

## Environment

`.env` file (copy from `.env.example`):
- `ALFRED_API_KEY` — Bearer token for API auth (all endpoints except /health)
- `THINGS_MCP_URL` — MCP server URL (default: http://127.0.0.1:8100)
- `TELEGRAM_BOT_TOKEN` — Telegram Bot API token
- `ANTHROPIC_API_KEY` — Claude API key
- `CLAUDE_MODEL` — Model ID (default: claude-sonnet-4-20250514)

## Gotchas

- MCP server (things-mcp) must be running on port 8100 as a separate process
- API requires Bearer token auth on all endpoints except `/health`
- Uses UV package manager, not pip
- launchd plist is `com.rickarmbrust.things-agent` (not `alfred`)
- Port 8200 chosen to avoid conflict with sherlock-hq (8300) and things-mcp (8100)
