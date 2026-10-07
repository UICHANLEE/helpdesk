"""Reassess generic unanswered incidents using already retrieved verified history."""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from incident import PLAYBOOKS

from backend.knowledge.fallback import from_verified_history
from backend.models import AgentAction, ClaimReference, IncidentState, IncidentStatus, TraceClaim
from backend.storage import sqlite as storage


def reassess(incident_id: str) -> bool:
    record = storage.get_incident(incident_id)
    if not record:
        return False
    state = IncidentState.model_validate(record["state"])
    if (state.origin != "live" or state.status != IncidentStatus.action_required or state.resolution or
            state.diagnosis != PLAYBOOKS["UNKNOWN"][0] or state.providerStatus.get("qwen") == "connected"):
        return False
    fallback = from_verified_history([match.model_dump() for match in state.raftMatches])
    if not fallback:
        return False
    retrieval = next((event for event in storage.get_events(incident_id) if event["type"] == "retrieval"), None)
    state.diagnosis = fallback["diagnosis"]
    state.immediateActions = fallback["immediate_actions"]
    state.recommendedAction = fallback["recommended_action"]
    state.actions = [AgentAction(id=f"{incident_id}-A1", label=state.recommendedAction)]
    state.providerStatus["answer_source"] = "verified_history_check"
    state.reasoningTrace = [
        {"step": "OBSERVATION", "text": "; ".join(state.symptoms)},
        {"step": "INTERPRETATION", "text": state.classification.domain if state.classification else "UNKNOWN"},
        {"step": "EVIDENCE", "text": f"과거 해결 기록 {fallback['historical_case_id']} 참고 (현재 건 검증 전)"},
        {"step": "HYPOTHESIS", "text": state.diagnosis},
        {"step": "NEXT TEST", "text": state.recommendedAction},
    ]
    event = storage.append_event(incident_id, "historical_reassessment", {
        "historical_case_id": fallback["historical_case_id"], "diagnosis": state.diagnosis,
        "recommended_action": state.recommendedAction, "verification": "unverified",
        "retrieval_event_id": retrieval["id"] if retrieval else None,
    })
    state.claims.append(TraceClaim(id=f"{incident_id}-C{len(state.claims) + 1}", text=state.diagnosis,
                                   verification="unverified", references=[ClaimReference(
                                       eventId=retrieval["id"] if retrieval else event["id"],
                                       relation="historical_match")],
                                   createdAt=datetime.now(timezone.utc).isoformat()))
    storage.save_state(state)
    return True


if __name__ == "__main__":
    for target in sys.argv[1:]:
        print(f"{target}: {'updated' if reassess(target) else 'unchanged'}")
