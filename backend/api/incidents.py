from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timezone
import time

from backend.storage import sqlite as storage
from backend.models import AgentAction, ClaimReference, ExampleReviewRequest, IncidentState, IncidentStatus, StatusUpdateRequest, TraceClaim, WorkflowStage, WorkflowUpdateRequest
from backend.agent.orchestrator import publish, rehearse_example, span
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
    if state.origin == "example":
        raise HTTPException(status_code=409, detail="예시 질문은 연습 검토 기능에서 수정하세요.")
    if request.status.value == "resolved":
        if not request.root_cause or not request.root_cause.strip() or not request.successful_action or not request.successful_action.strip():
            raise HTTPException(status_code=422, detail="확인된 원인과 실제 성공한 조치를 입력하세요.")
        state.resolution = {"rootCause": request.root_cause.strip(), "successfulAction": request.successful_action.strip(),
                            "note": (request.note or "").strip(), "verifiedAt": datetime.now(timezone.utc).isoformat()}
        state.diagnosis = request.root_cause.strip()
    state.status = request.status
    if request.status == IncidentStatus.resolved:
        state.workflowStage = WorkflowStage.done
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


@router.patch("/incidents/{incident_id}/workflow")
async def update_workflow(incident_id: str, request: WorkflowUpdateRequest) -> dict:
    incident = require_incident(incident_id)
    state = IncidentState.model_validate(incident["state"])
    if state.origin == "example":
        raise HTTPException(status_code=409, detail="연습 사례는 업무 보드에 포함되지 않습니다.")
    if state.status == IncidentStatus.resolved:
        raise HTTPException(status_code=409, detail="해결된 Incident는 완료 상태로 유지됩니다.")
    if state.status == IncidentStatus.investigating:
        raise HTTPException(status_code=409, detail="자동 진단이 끝난 뒤 업무 단계를 이동할 수 있습니다.")
    if request.stage == WorkflowStage.done:
        raise HTTPException(status_code=422, detail="완료하려면 확인된 원인과 실제 조치를 해결 기록에 입력하세요.")
    if request.stage == WorkflowStage.review and state.status not in (IncidentStatus.action_required, IncidentStatus.verifying):
        raise HTTPException(status_code=409, detail="진단이 끝난 뒤 검토 단계로 이동할 수 있습니다.")
    state.workflowStage = request.stage
    storage.save_state(state)
    await publish(incident_id, "workflow_changed", {"stage": request.stage.value, "manual": True})
    return state.model_dump()


@router.post("/incidents/{incident_id}/rehearse", status_code=202)
async def start_rehearsal(incident_id: str) -> dict:
    try:
        classification, _task = await rehearse_example(incident_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"incident_id": incident_id, "classification": classification.model_dump(), "status": "investigating"}


@router.post("/incidents/{incident_id}/example-review")
async def review_example(incident_id: str, request: ExampleReviewRequest) -> dict:
    incident = require_incident(incident_id)
    state = IncidentState.model_validate(incident["state"])
    if state.origin != "example" or state.examplePhase not in ("awaiting_review", "reviewed"):
        raise HTTPException(status_code=409, detail="진단이 끝난 예시만 검토할 수 있습니다.")
    if not request.root_cause.strip() or not request.successful_action.strip():
        raise HTTPException(status_code=422, detail="원인과 조치를 입력하세요.")
    original = state.firstDiagnosis or ""
    state.diagnosis = request.root_cause.strip()
    state.immediateActions = [request.successful_action.strip()]
    state.recommendedAction = request.successful_action.strip()
    state.actions.append(AgentAction(id=f"{incident_id}-A{len(state.actions) + 1}",
                                     label=state.recommendedAction, status="example_reviewed"))
    state.reasoningTrace.append({"step": "REFERENCE REVIEW", "text":
                                 f"첫 판단: {original} → 참고 답안: {state.diagnosis}"})
    state.resolution = {"rootCause": request.root_cause.strip(), "successfulAction": request.successful_action.strip(),
                        "note": request.note.strip(), "reviewedAt": datetime.now(timezone.utc).isoformat(),
                        "verification": "hypothetical_reference", "reviewSource": request.review_source}
    state.status = IncidentStatus.resolved
    state.currentStep = "verify"
    state.examplePhase = "reviewed"
    storage.save_state(state)
    event = await publish(incident_id, "example_reviewed", {
        "first_diagnosis": original, "revised_cause": state.diagnosis,
        "revised_action": state.recommendedAction, "note": request.note.strip(),
        "changed": original != state.diagnosis, "verification": "hypothetical_reference",
        "review_source": request.review_source})
    state.claims.append(TraceClaim(id=f"{incident_id}-C{len(state.claims) + 1}", text=state.diagnosis,
        verification="example", references=[ClaimReference(eventId=event["id"], relation="example_scenario")],
        createdAt=datetime.now(timezone.utc).isoformat()))
    storage.save_state(state)
    return state.model_dump()
