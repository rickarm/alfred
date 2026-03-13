"""MCP Streamable HTTP client using the official MCP Python SDK."""

import logging

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .config import settings

logger = logging.getLogger(__name__)


async def call_tool(tool_name: str, arguments: dict | None = None) -> list[dict]:
    """Call an MCP tool on the things-mcp server and return parsed results.

    Raises:
        RuntimeError: If the MCP server is unreachable or returns an error.
    """
    if arguments is None:
        arguments = {}

    try:
        async with streamable_http_client(
            url=settings.things_mcp_url,
            http_client=httpx.AsyncClient(timeout=httpx.Timeout(30, read=60)),
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)

        if not result.content:
            return []

        text = result.content[0].text if hasattr(result.content[0], "text") else ""
        return _parse_text_response(text)

    except httpx.ConnectError as e:
        raise RuntimeError(f"Cannot reach MCP server at {settings.things_mcp_url}: {e}") from e
    except Exception as e:
        logger.exception("MCP tool call failed: %s(%s)", tool_name, arguments)
        raise RuntimeError(f"MCP call failed: {e}") from e


def _parse_text_response(text: str) -> list[dict]:
    """Parse Things MCP key-value text blocks into a list of dicts.

    Each block is separated by '---' and contains lines of the form 'Key: value'.
    """
    if not text or not text.strip():
        return []

    records = []
    for block in text.split("\n---\n"):
        block = block.strip().strip("---").strip()
        if not block:
            continue
        record: dict = {}
        current_key: str | None = None
        current_lines: list[str] = []

        for line in block.split("\n"):
            if ": " in line and not line.startswith(" "):
                # Save previous key
                if current_key:
                    record[current_key] = "\n".join(current_lines).strip()
                key, _, value = line.partition(": ")
                current_key = _normalize_key(key)
                current_lines = [value]
            elif current_key and line.startswith(" "):
                current_lines.append(line.strip())
            elif current_key:
                current_lines.append(line)

        if current_key:
            record[current_key] = "\n".join(current_lines).strip()

        if record:
            records.append(record)

    return records


def _normalize_key(key: str) -> str:
    return key.lower().strip().replace(" ", "_").replace("-", "_")
