from fastapi import APIRouter, HTTPException

from backend.agent.orchestrator import publish
from backend.models import Evidence, IncidentState, ToolExecuteRequest
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
    if request.tool in get_tool_config():
        await publish(request.incident_id, "tool_started", {"tool": request.tool, "manual": True})
    result = await execute(request.tool, parse_incident(incident["message"]))
    state = IncidentState.model_validate(incident["state"])
    evidence = Evidence(id=f"E{len(state.confirmedFacts) + 1}", source=request.tool, summary=str(result["summary"]), status="confirmed" if result["status"] == "ok" else "unavailable", data=result.get("data") if isinstance(result.get("data"), dict) else None)
    if evidence.status == "confirmed":
        state.confirmedFacts.append(evidence)
        storage.save_state(state)
    await publish(request.incident_id, "tool_result", {"tool": request.tool, "result": result, "evidence": evidence.model_dump(), "manual": True})
    return result
