# things-agent

FastAPI REST gateway for Things 3, wrapping the `hald/things-mcp` MCP server.

## Architecture

```
Telegram Bot (Phase 3)
       ↓
FastAPI Gateway  ← this service, port 8200
       ↓
things-mcp MCP Server (port 8100)
       ↓
Things 3 (macOS app)
```

## Setup

```bash
cp .env.example .env
# Edit .env with your API key
uv sync
uv run uvicorn src.main:app --host 0.0.0.0 --port 8200
```

## API

All endpoints require `Authorization: Bearer <key>` except `/api/v1/health`.

### Read

```
GET /api/v1/health
GET /api/v1/lists/{inbox|today|upcoming|anytime|someday|logbook|trash}
GET /api/v1/projects[?include_items=true]
GET /api/v1/projects/{uuid}/tasks
GET /api/v1/areas
GET /api/v1/tags
GET /api/v1/tags/{tag}/items
GET /api/v1/search?q=keyword
GET /api/v1/search/advanced?status=&tag=&area=&last=
GET /api/v1/recent?period=3d
```

### Write

```
POST  /api/v1/todos          {"title": "...", "notes": "...", "when": "today"}
PATCH /api/v1/todos/{id}     {"completed": true}
POST  /api/v1/projects       {"title": "...", "area_id": "..."}
PATCH /api/v1/projects/{id}  {"title": "..."}
```

## launchd

```bash
make start    # load service
make stop     # unload service
make restart  # reload
make logs     # tail stdout
make errors   # tail stderr
make health   # quick health check
```
