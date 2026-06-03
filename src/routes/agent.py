"""Natural-language agent endpoint — free-text in, Things edits out.

Mirrors the Telegram free-text path so an agent in a VM/container can drive
Things 3 over HTTP when the native app / MCP / AppleScript paths aren't reachable.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import agent
from ..auth import require_api_key
from ..skills import registry

router = APIRouter(prefix="/api/v1")

Auth = Annotated[str, Depends(require_api_key)]


class MessageRequest(BaseModel):
    message: str


@router.post("/message")
async def post_message(body: MessageRequest, _: Auth) -> dict:
    """Run the Claude agent loop on a free-text message and return its reply.

    Uses the same tools + executor as the Telegram bot, so edits execute
    immediately and the reply describes what changed.
    """
    reply = await agent.run(body.message, registry.all_tools(), registry.execute_tool)
    return {
        "ok": True,
        "data": {"reply": reply},
        "meta": {"timestamp": datetime.now(UTC).isoformat()},
    }
