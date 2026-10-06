"""Combine external RAFT matches with verified local incident and FAQ knowledge."""

import asyncio
import os
from typing import Any

from incident import search_raft
from backend.knowledge.service import search


async def retrieve(parsed: dict[str, Any], judgment: dict[str, Any], exclude_id: str | None = None) -> list[dict[str, Any]]:
    if os.getenv("RAFT_SEARCH_URL"):
        remote = await asyncio.to_thread(search_raft, parsed, judgment)
    else:
        remote = []
    local = await asyncio.to_thread(search, parsed["text"], 5, exclude_id)
    matches = list(remote)
    seen = {item["id"] for item in remote}
    for item in local:
        if item["id"] in seen:
            continue
        verified = item["status"] == "verified"
        matches.append({"id": item["id"], "title": item["answer"][:120] if verified else "유사한 미해결 질문",
                        "summary": (f"확인된 해결 사례 | 질문: {item['question'][:180]} | 조치: {'; '.join(item['actions'])[:180]}"
                                    if verified else f"미검증 유사 질문 (해결 근거 아님): {item['question'][:180]}"),
                        "score": item["score"], "verification": item["status"], "retrieval": item["retrieval"]})
        if len(matches) == 3:
            break
    return matches[:3]
