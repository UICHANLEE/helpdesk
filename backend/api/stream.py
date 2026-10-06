from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from backend.agent.orchestrator import stream
from backend.api.incidents import require_incident
from backend.storage import sqlite as storage

router = APIRouter()


@router.get("/incidents/{incident_id}/stream")
async def incident_stream(incident_id: str, request: Request, last_event_id: str | None = Header(default=None)) -> StreamingResponse:
    require_incident(incident_id)
    try:
        after = max(0, int(last_event_id or 0))
    except ValueError:
        after = 0

    async def events() -> AsyncIterator[str]:
        if storage.cloud_mode():
            for event in storage.get_events(incident_id, after):
                yield f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            return
        async for event in stream(incident_id, after):
            if await request.is_disconnected():
                break
            if event is None:
                yield ": heartbeat\n\n"
            else:
                yield f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
