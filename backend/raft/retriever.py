"""Combine external RAFT matches with verified local incident and FAQ knowledge."""

import asyncio
import os
from typing import Any

from incident import search_raft
from backend.knowledge.service import search


async def retrieve(parsed: dict[str, Any], judgment: dict[str, Any]) -> list[dict[str, Any]]:
    if os.getenv("RAFT_SEARCH_URL"):
        remote = await asyncio.to_thread(search_raft, parsed, judgment)
    else:
        remote = []
    local = search(parsed["text"], limit=5)
    matches = list(remote)
    seen = {item["id"] for item in remote}
    for item in local:
        if item["id"] in seen:
            continue
        matches.append({"id": item["id"], "title": item["answer"][:120],
                        "summary": f"질문: {item['question'][:180]} | 조치: {'; '.join(item['actions'])[:180]}",
                        "score": round(min(.99, item["score"] / (item["score"] + 2)), 3)})
        if len(matches) == 3:
            break
    return matches[:3]
