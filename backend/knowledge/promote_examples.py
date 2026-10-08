"""Materialize prepared question, situation, cause and action as labeled case resolutions."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from backend.knowledge import service, vector
from backend.models import Classification, IncidentState, IncidentStatus, WorkflowStage
from backend.storage import sqlite as storage

BACKUP_DIR = Path(__file__).resolve().parents[1] / "backups"


def backup_before_promotion() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = BACKUP_DIR / f"pre-example-promotion-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.sqlite3"
    with sqlite3.connect(storage.DB_PATH) as original, sqlite3.connect(path) as snapshot:
        original.backup(snapshot)
    path.chmod(0o600)
    return path


def promote(*, index_vectors: bool = True) -> dict[str, object]:
    storage.init_db()
    promoted = 0
    kept_reviewed = 0
    for item in storage.list_incidents("examples"):
        state = IncidentState.model_validate(item["state"])
        if state.examplePhase == "reviewed" and state.resolution:
            kept_reviewed += 1
            continue
        if state.examplePhase == "preloaded" and state.resolution:
            continue
        reference = state.exampleReference or {}
        cause = reference.get("rootCause", "").strip()
        action = reference.get("successfulAction", "").strip()
        situation = reference.get("situation", "").strip()
        domain = reference.get("domain", "UNKNOWN")
        if not cause or not action or not situation:
            raise ValueError(f"Missing prepared answer for {item['id']}")
        state.classification = Classification(domain=domain, source="preloaded_case")
        state.symptoms = [situation]
        state.diagnosis = cause
        state.immediateActions = [action]
        state.recommendedAction = action
        state.resolution = {"rootCause": cause, "successfulAction": action,
                            "note": "사전 작성한 가상 해결 예시. 실제 장애에서 검증된 조치가 아님.",
                            "reviewedAt": datetime.now(timezone.utc).isoformat(),
                            "verification": "hypothetical_reference", "reviewSource": "preloaded_case"}
        state.examplePhase = "preloaded"
        state.status = IncidentStatus.resolved
        state.workflowStage = WorkflowStage.done
        state.currentStep = "verify"
        storage.save_state(state)
        storage.append_event(item["id"], "example_preloaded", {
            "root_cause": cause, "successful_action": action,
            "verification": "hypothetical_reference", "source": "preloaded_case"})
        promoted += 1
    indexed = vector.sync(service.corpus_documents()) if index_vectors else 0
    return {"promoted": promoted, "kept_reviewed": kept_reviewed,
            "total_examples": len(storage.list_incidents("examples")), "indexed_documents": indexed,
            "vector_total": vector.status()["indexed"]}


if __name__ == "__main__":
    storage.init_db()
    pending = any(item["state"].get("examplePhase") not in ("reviewed", "preloaded")
                  for item in storage.list_incidents("examples"))
    backup = str(backup_before_promotion()) if pending else None
    print(json.dumps({"backup": backup, **promote()}, ensure_ascii=False))
