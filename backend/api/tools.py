from fastapi import APIRouter, HTTPException
import time
from datetime import datetime, timezone

from backend.agent.orchestrator import publish, span
from backend.models import ClaimReference, Evidence, IncidentState, ToolExecuteRequest
from backend.storage import sqlite as storage
from backend.tools.registry import ALLOWED_TOOLS, execute
from incident import get_tool_config, parse_incident

router = APIRouter()


@router.get("/tools")
def list_tools() -> list[dict]:
    from incident import get_tool_config
    configured = get_tool_config()
    return [{"name": name, "configured": name in configured, "mode": "read_only"} for name in sorted(ALLOWED_TOOLS)]


@router.post("/tools/execute")
async def execute_tool(request: ToolExecuteRequest) -> dict:
    incident = storage.get_incident(request.incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if request.tool not in ALLOWED_TOOLS:
        raise HTTPException(status_code=400, detail="Unknown or non-read-only tool")
    tool_span = span(request.incident_id, "tool", request.tool)
    if request.tool in get_tool_config():
        await publish(request.incident_id, "tool_started", {"tool": request.tool, "manual": True, "trace": tool_span})
    started = time.perf_counter()
    result = await execute(request.tool, parse_incident(incident["message"]))
    duration_ms = round((time.perf_counter() - started) * 1000)
    state = IncidentState.model_validate(incident["state"])
    evidence_status = "confirmed" if result["status"] == "ok" else "failed" if result["status"] == "error" else "unavailable"
    evidence = Evidence(id=f"E{len(state.confirmedFacts) + 1}", source=request.tool, summary=str(result["summary"]), status=evidence_status, data=result.get("data") if isinstance(result.get("data"), dict) else None)
    if evidence.status == "confirmed":
        state.confirmedFacts.append(evidence)
        storage.save_state(state)
    event = await publish(request.incident_id, "tool_result", {"tool": request.tool, "result": result, "evidence": evidence.model_dump(), "manual": True,
        "trace": {**tool_span, "ended_at": datetime.now(timezone.utc).isoformat(),
                  "duration_ms": duration_ms, "status": result["status"]}})
    if result["status"] != "unconfigured" and state.status.value != "resolved":
        claim = next((item for item in reversed(state.claims) if item.verification == "unverified"), None)
        if claim:
            claim.references.append(ClaimReference(eventId=event["id"], relation="follow_up_check"))
            storage.save_state(state)
    return result
