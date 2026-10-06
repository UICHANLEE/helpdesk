from fastapi import APIRouter, HTTPException

from backend.agent.orchestrator import publish
from backend.models import IncidentState
from backend.storage import sqlite as storage

router = APIRouter()


async def decide(action_id: str, decision: str) -> dict:
    incident_id = action_id.rsplit("-A", 1)[0]
    incident = storage.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    state = IncidentState.model_validate(incident["state"])
    action = next((item for item in state.actions if item.id == action_id), None)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    action.status = decision
    storage.record_action(action_id, incident_id, decision)
    storage.save_state(state)
    await publish(incident_id, "action", {"action_id": action_id, "decision": decision, "execution": "not_executed"})
    return {"action_id": action_id, "decision": decision, "execution": "not_executed"}


@router.post("/actions/{action_id}/approve")
async def approve(action_id: str) -> dict:
    return await decide(action_id, "approved")


@router.post("/actions/{action_id}/reject")
async def reject(action_id: str) -> dict:
    return await decide(action_id, "rejected")
