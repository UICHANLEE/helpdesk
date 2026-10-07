"""Reassess generic unanswered incidents using already retrieved verified history."""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from incident import PLAYBOOKS, parse_incident, rule_judgment

from backend.knowledge.fallback import from_verified_history
from backend.models import AgentAction, ClaimReference, Classification, Hypothesis, IncidentState, IncidentStatus, TraceClaim
from backend.storage import sqlite as storage


def reassess(incident_id: str) -> bool:
    record = storage.get_incident(incident_id)
    if not record:
        return False
    state = IncidentState.model_validate(record["state"])
    if state.providerStatus.get("answer_source") == "verified_history_check":
        fallback = from_verified_history([match.model_dump() for match in state.raftMatches])
        if fallback and fallback["historical_case_id"] in state.diagnosis and (
                not state.hypotheses or state.hypotheses[0].name != fallback["hypotheses"][0]["name"]):
            state.hypotheses = [Hypothesis(id="H1", **fallback["hypotheses"][0])]
            storage.save_state(state)
            return True
        return False
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
    state.hypotheses = [Hypothesis(id="H1", **fallback["hypotheses"][0])]
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


def reclassify_explicit_llm(incident_id: str) -> bool:
    record = storage.get_incident(incident_id)
    if not record:
        return False
    state = IncidentState.model_validate(record["state"])
    if not state.classification or state.classification.domain != "UNKNOWN":
        return False
    judgment = rule_judgment(parse_incident(record["message"]))
    if judgment["primary"] != "LLM":
        return False
    state.classification = Classification(domain="LLM", severity=state.classification.severity,
                                          complexity=state.classification.complexity, source="rules_override")
    storage.append_event(incident_id, "classification_revised", {
        "previous_domain": "UNKNOWN", "domain": "LLM", "source": "explicit_question_signal",
    })
    storage.save_state(state)
    return True


if __name__ == "__main__":
    for target in sys.argv[1:]:
        revised = reclassify_explicit_llm(target)
        updated = reassess(target)
        print(f"{target}: {'reclassified ' if revised else ''}{'reassessed' if updated else 'unchanged'}")
