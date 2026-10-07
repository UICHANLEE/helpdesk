"""Install 100 hypothetical HelpDesk incidents without running the agent or external tools."""

from __future__ import annotations

import csv
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from incident import CATEGORIES

from backend.knowledge import service, vector
from backend.models import AgentAction, ClaimReference, Classification, IncidentState, IncidentStatus, TraceClaim
from backend.storage import sqlite as storage

CASES_PATH = Path(__file__).with_name("example_cases.tsv")
BACKUP_DIR = Path(__file__).resolve().parents[1] / "backups"


def load_cases(path: Path = CASES_PATH) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        cases = list(csv.DictReader(source, delimiter="\t"))
    groups = Counter(item["group"] for item in cases)
    if groups != {"conversation": 50, "general": 50}:
        raise ValueError(f"Expected 50 conversation and 50 general cases, got {groups}")
    questions = [item["question"].strip() for item in cases]
    if len(set(questions)) != 100:
        raise ValueError("Example questions must be unique")
    required = ("group", "domain", "question", "situation", "root_cause", "successful_action")
    if any(not all(item.get(key, "").strip() for key in required) or item["domain"] not in CATEGORIES for item in cases):
        raise ValueError("Example case has missing fields or unknown domain")
    return cases


def backup_before_seed() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = BACKUP_DIR / f"pre-example-seed-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.sqlite3"
    with sqlite3.connect(storage.DB_PATH) as original, sqlite3.connect(path) as snapshot:
        original.backup(snapshot)
    path.chmod(0o600)
    return path


def seed_examples(path: Path = CASES_PATH, index_vectors: bool = True) -> dict[str, object]:
    cases = load_cases(path)
    storage.init_db()
    existing = {item["state"].get("seedKey"): item for item in storage.list_all_incidents()
                if item["state"].get("origin") == "example"}
    created: list[str] = []
    repaired = 0
    for group, group_cases in ((name, [case for case in cases if case["group"] == name])
                               for name in ("conversation", "general")):
        for number, case in enumerate(group_cases, 1):
            key = f"{group}-{number:03d}"
            prior = existing.get(key)
            prior_events = storage.get_events(prior["id"]) if prior else []
            if (prior and prior["state"].get("status") == "resolved" and prior["state"].get("resolution")
                    and prior["state"].get("claims") and any(event["type"] == "status_changed" for event in prior_events)):
                continue
            if prior:
                state = IncidentState.model_validate(prior["state"])
                incident_id = prior["id"]
                repaired += 1
            else:
                state = IncidentState(id="", origin="example", seedKey=key,
                                      status=IncidentStatus.investigating,
                                      classification=Classification(domain=case["domain"], source="example"),
                                      symptoms=[case["situation"]], currentStep="observe",
                                      providerStatus={"jev": "not_run", "raft": "not_run", "qwen": "not_run"})
                incident_id = storage.create_incident(case["question"], state)
                created.append(incident_id)
            state.traceId = f"TR-{incident_id}"
            user_event = next((event for event in prior_events if event["type"] == "user"), None)
            if not user_event:
                user_event = storage.append_event(incident_id, "user", {
                    "message": case["question"], "origin": "example", "seed_key": key})
            state.diagnosis = case["root_cause"]
            state.immediateActions = [case["successful_action"]]
            state.recommendedAction = case["successful_action"]
            state.actions = [AgentAction(id=f"{incident_id}-A1", label=case["successful_action"], status="example")]
            state.reasoningTrace = [
                {"step": "SCENARIO", "text": case["situation"]},
                {"step": "ASSUMED CAUSE", "text": case["root_cause"]},
                {"step": "ILLUSTRATIVE ACTION", "text": case["successful_action"]},
            ]
            state.resolution = {"rootCause": case["root_cause"],
                                "successfulAction": case["successful_action"],
                                "note": "학습용 가상 시나리오. 실제 장애의 원인·조치로 검증되지 않았습니다.",
                                "recordedAt": datetime.now(timezone.utc).isoformat()}
            state.status = IncidentStatus.resolved
            state.currentStep = "verify"
            storage.save_state(state)
            resolution_event = next((event for event in prior_events if event["type"] == "status_changed"), None)
            if not resolution_event:
                resolution_event = storage.append_event(incident_id, "status_changed", {
                    "status": "resolved", "manual": False, "origin": "example", "resolution": state.resolution,
                    "trace": {"trace_id": state.traceId, "kind": "example", "status": "example"}})
            state.claims = [TraceClaim(id=f"{incident_id}-C1", text=case["root_cause"],
                                       verification="example", references=[
                                           ClaimReference(eventId=user_event["id"], relation="reported"),
                                           ClaimReference(eventId=resolution_event["id"], relation="example_scenario")],
                                       createdAt=datetime.now(timezone.utc).isoformat())]
            storage.save_state(state)
    indexed = 0
    if index_vectors:
        indexed = vector.sync(service.corpus_documents())
    return {"created": len(created), "repaired": repaired, "example_total": len(cases), "ids": created,
            "indexed_documents": indexed, "vector_total": vector.status()["indexed"]}


if __name__ == "__main__":
    import json

    storage.init_db()
    cases = load_cases()
    already = sum(item["state"].get("origin") == "example" for item in storage.list_all_incidents())
    backup = str(backup_before_seed()) if already < len(cases) else None
    print(json.dumps({"backup": backup, **seed_examples()}, ensure_ascii=False))
