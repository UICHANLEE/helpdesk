"""Jev classification. The existing rule parser is the explicit fallback."""

import asyncio
from typing import Any

from incident import jev_judgment, parse_incident, rule_judgment


async def classify(message: str) -> tuple[dict[str, Any], dict[str, Any]]:
    parsed = parse_incident(message)
    fallback = rule_judgment(parsed)
    result = await asyncio.to_thread(jev_judgment, parsed, fallback)
    return parsed, result
