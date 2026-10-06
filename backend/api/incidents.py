from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timezone
import time

from backend.storage import sqlite as storage
from backend.models import ClaimReference, IncidentState, StatusUpdateRequest, TraceClaim
from backend.agent.orchestrator import publish, span
from backend.observability.trace import graph

router = APIRouter()


def require_incident(incident_id: str) -> dict:
    incident = storage.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.get("/incidents")
def list_incidents(status: str | None = Query(default=None)) -> list[dict]:
    return storage.list_incidents(status)


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> dict:
    return require_incident(incident_id)


@router.get("/incidents/{incident_id}/state")
def get_state(incident_id: str) -> dict:
    return require_incident(incident_id)["state"]


@router.get("/incidents/{incident_id}/events")
def get_events(incident_id: str) -> list[dict]:
    require_incident(incident_id)
    return storage.get_events(incident_id)


@router.get("/incidents/{incident_id}/trace")
def get_trace(incident_id: str) -> dict:
    return graph(require_incident(incident_id), storage.get_events(incident_id))


@router.get("/traces/{trace_id}")
def find_trace(trace_id: str) -> dict:
    if not trace_id.startswith("TR-INC-"):
        raise HTTPException(status_code=404, detail="Trace not found")
    return get_trace(trace_id[3:])


@router.patch("/incidents/{incident_id}/status")
async def update_status(incident_id: str, request: StatusUpdateRequest) -> dict:
    started = time.perf_counter()
    verification_span = span(incident_id, "verification", "operator status update")
    incident = require_incident(incident_id)
    state = IncidentState.model_validate(incident["state"])
    if request.status.value == "resolved":
        if not request.root_cause or not request.root_cause.strip() or not request.successful_action or not request.successful_action.strip():
            raise HTTPException(status_code=422, detail="확인된 원인과 실제 성공한 조치를 입력하세요.")
        state.resolution = {"rootCause": request.root_cause.strip(), "successfulAction": request.successful_action.strip(),
                            "note": (request.note or "").strip(), "verifiedAt": datetime.now(timezone.utc).isoformat()}
        state.diagnosis = request.root_cause.strip()
    state.status = request.status
    state.currentStep = "verify" if request.status.value in ("verifying", "resolved") else state.currentStep
    storage.save_state(state)
    event = await publish(incident_id, "status_changed", {"status": request.status.value, "manual": True,
        "resolution": state.resolution if request.status.value == "resolved" else None,
        "trace": {**verification_span, "ended_at": datetime.now(timezone.utc).isoformat(),
                  "duration_ms": round((time.perf_counter() - started) * 1000),
                  "status": "operator_verified" if request.status.value == "resolved" else "updated"}})
    if request.status.value == "resolved":
        state.claims.append(TraceClaim(id=f"{incident_id}-C{len(state.claims) + 1}", text=request.root_cause.strip(),
            verification="operator_verified", references=[ClaimReference(eventId=event["id"], relation="operator_verification")],
            createdAt=datetime.now(timezone.utc).isoformat()))
        storage.save_state(state)
    return state.model_dump()
