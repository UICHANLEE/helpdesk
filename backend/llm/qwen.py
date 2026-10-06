"""OpenAI-compatible Qwen adapter. Unavailable model leaves an honest rule result."""

import asyncio
from typing import Any

from incident import qwen_diagnosis


async def diagnose(parsed: dict[str, Any], judgment: dict[str, Any], context: dict[str, Any]) -> dict[str, Any] | None:
    return await asyncio.to_thread(qwen_diagnosis, parsed, judgment, context)
