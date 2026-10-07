"""Install 100 question prompts awaiting a real investigation and review."""

from __future__ import annotations

import csv
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from incident import CATEGORIES

from backend.knowledge import service, vector
from backend.models import IncidentState, IncidentStatus
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
            reference = {"situation": case["situation"], "rootCause": case["root_cause"],
                         "successfulAction": case["successful_action"]}
            if prior:
                state = IncidentState.model_validate(prior["state"])
                incident_id = prior["id"]
                if state.examplePhase:
                    continue
                repaired += 1
            else:
                state = IncidentState(id="", origin="example", seedKey=key,
                                      status=IncidentStatus.new, symptoms=[case["situation"]],
                                      providerStatus={"jev": "not_run", "raft": "not_run", "qwen": "not_run"})
                incident_id = storage.create_incident(case["question"], state)
                created.append(incident_id)
            state.traceId = f"TR-{incident_id}"
            state.examplePhase = "seeded"
            state.exampleReference = reference
            state.status = IncidentStatus.new
            state.currentStep = "observe"
            state.classification = None
            state.diagnosis = ""
            state.immediateActions = []
            state.recommendedAction = ""
            state.actions = []
            state.raftMatches = []
            state.confirmedFacts = []
            state.hypotheses = []
            state.reasoningTrace = []
            state.resolution = None
            state.claims = []
            storage.save_state(state)
            if not prior:
                storage.append_event(incident_id, "example_seeded", {"message": case["question"], "seed_key": key})
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
