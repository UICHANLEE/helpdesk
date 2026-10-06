"""Read-only tool allowlist. Endpoints are configured by an operator."""

import asyncio
from typing import Any

from incident import ROUTES, run_tool, selected_tools

ALLOWED_TOOLS = frozenset(tool for tools in ROUTES.values() for tool in tools)


def tools_for(judgment: dict[str, Any]) -> list[str]:
    return selected_tools(judgment)


async def execute(name: str, parsed: dict[str, Any]) -> dict[str, Any]:
    if name not in ALLOWED_TOOLS:
        raise ValueError("Tool is not in the read-only allowlist")
    return await asyncio.to_thread(run_tool, name, parsed)
