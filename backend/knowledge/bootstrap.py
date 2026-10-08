"""Index fictional troubleshooting patterns as a local, clearly labeled case memory."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.knowledge.generate_scenarios import OUTPUT, PATTERNS, build_cases, load_patterns
from backend.storage import sqlite as storage

VERSION = "synthetic-case-memory-v1"


def _manifest_path() -> Path:
    return storage.DB_PATH.with_suffix(".bootstrap.json")


def _source_hash() -> str:
    digest = hashlib.sha256()
    for path in (PATTERNS, OUTPUT):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def status() -> dict[str, Any]:
    path = _manifest_path()
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    active = saved.get("version") == VERSION and saved.get("source_hash") == _source_hash()
    return {"active": active, "patterns": 100 if active else 0,
            "question_variants": 900 if active else 0,
            "trained_at": saved.get("trained_at") if active else None,
            "mode": "synthetic_rag_memory", "model_fine_tuned": False}


def documents(*, include_inactive: bool = False) -> list[dict[str, Any]]:
    if not include_inactive and not status()["active"]:
        return []
    patterns = load_patterns()
    variants = build_cases(patterns)
    result = []
    for index, pattern in enumerate(patterns):
        aliases = [item["question"] for item in variants[index * 9:(index + 1) * 9]]
        # build_cases emits nine adjacent question forms for each source pattern.
        result.append({"id": f"PATTERN-{index + 1:03d}", "type": "pattern",
                       "question": pattern["symptom"], "answer": pattern["root_cause"],
                       "actions": [pattern["check"], pattern["successful_action"]],
                       "status": "synthetic", "domain": pattern["domain"],
                       "evidence": pattern["evidence"], "aliases": " ".join(aliases),
                       "content": (f"영역: {pattern['domain']} 질문: {pattern['symptom']} "
                                   f"가상 관찰: {pattern['evidence']} 가정 원인: {pattern['root_cause']} "
                                   f"확인 절차: {pattern['check']} 참고 조치: {pattern['successful_action']}")})
    return result


def train() -> dict[str, Any]:
    """Build the persistent vector index before enabling synthetic memory for searches."""
    from backend.knowledge import service, vector

    storage.init_db()
    patterns = documents(include_inactive=True)
    if len(patterns) != 100:
        raise ValueError("Expected 100 distinct training patterns")
    existing = [item for item in service.corpus_documents() if item["type"] != "pattern"]
    indexed = vector.sync(existing + patterns)
    indexed_ids = {row["document_id"] for row in storage.list_vectors(vector.MODEL)}
    if not all(item["id"] in indexed_ids for item in patterns):
        raise RuntimeError("Pattern embeddings are incomplete; case memory was not activated")
    marker = {"version": VERSION, "source_hash": _source_hash(),
              "trained_at": datetime.now(timezone.utc).isoformat()}
    path = _manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(marker), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    return {**status(), "new_embeddings": indexed, "vector_total": len(indexed_ids)}


if __name__ == "__main__":
    print(json.dumps(train(), ensure_ascii=False))
