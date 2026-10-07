"""Run seeded questions through the live agent, then compare and correct against reference answers."""

from __future__ import annotations

import argparse
import asyncio
import json

from backend.agent.orchestrator import rehearse_example
from backend.api.incidents import review_example
from backend.models import ExampleReviewRequest, IncidentState, IncidentStatus
from backend.storage import sqlite as storage


async def run(limit: int = 100, require_qwen: bool = True) -> dict[str, object]:
    examples = [item for item in reversed(storage.list_incidents("examples"))
                if item["state"].get("examplePhase") in ("seeded", "investigating", "awaiting_review")]
    completed: list[str] = []
    awaiting: list[str] = []
    for item in examples[:limit]:
        incident_id = item["id"]
        current = item["state"]
        if current.get("examplePhase") == "investigating":
            state = IncidentState.model_validate(current)
            state.examplePhase = "seeded"
            state.status = IncidentStatus.new
            storage.save_state(state)
            storage.append_event(incident_id, "rehearsal_interrupted", {"reason": "previous batch stopped; retrying"})
            current = state.model_dump()
        if current.get("examplePhase") == "seeded" or (current.get("examplePhase") == "awaiting_review" and
            current.get("providerStatus", {}).get("qwen") != "connected"):
            _, task = await rehearse_example(incident_id)
            await task
            current = storage.get_incident(incident_id)["state"]
        if current.get("examplePhase") != "awaiting_review":
            awaiting.append(incident_id)
            print(json.dumps({"incident_id": incident_id, "stage": "investigation_failed"}), flush=True)
            continue
        if require_qwen and current.get("providerStatus", {}).get("qwen") != "connected":
            awaiting.append(incident_id)
            print(json.dumps({"incident_id": incident_id, "stage": "qwen_unavailable"}), flush=True)
            continue
        reference = current.get("exampleReference") or {}
        await review_example(incident_id, ExampleReviewRequest(
            root_cause=reference["rootCause"], successful_action=reference["successfulAction"],
            note="첫 진단을 참고 답안과 비교하여 수정함. 가상 시나리오이며 실제 장애 검증은 아님.",
            review_source="reference_batch"))
        completed.append(incident_id)
        print(json.dumps({"incident_id": incident_id, "stage": "reviewed",
                          "qwen": current["providerStatus"]["qwen"],
                          "first_diagnosis": current.get("firstDiagnosis"),
                          "revised_cause": reference["rootCause"]}, ensure_ascii=False), flush=True)
    return {"reviewed": len(completed), "awaiting": awaiting, "ids": completed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--allow-rule-fallback", action="store_true")
    args = parser.parse_args()
    storage.init_db()
    print(json.dumps(asyncio.run(run(args.limit, not args.allow_rule_fallback)), ensure_ascii=False), flush=True)
