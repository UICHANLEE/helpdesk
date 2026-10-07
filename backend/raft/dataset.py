"""Local, auditable RAFT-style SFT examples from operator-verified incidents.

The paper's oracle-free examples teach recall. For incident operations we instead
teach abstention when the supplied documents do not support the answer.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from backend.raft.sparse import rank
from backend.storage import sqlite as storage

SCHEMA_VERSION = "helpdesk-raft-v1"
SYSTEM = ("당신은 HelpDesk 진단 보조자입니다. 제공된 문서에서 확인된 사실만 답하세요. "
          "관련 없는 문서는 무시하고, 원인과 조치는 근거 Incident ID를 표시하세요. "
          "근거가 없으면 원인을 추정하지 말고 추가 확인이 필요하다고 답하세요.")


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _case(item: dict[str, Any]) -> dict[str, str] | None:
    state = item["state"]
    resolution = state.get("resolution") or {}
    if (state.get("origin", "live") != "live" or state.get("status") != "resolved"
            or not resolution.get("verifiedAt") or not item["message"].strip()
            or not resolution.get("rootCause", "").strip()
            or not resolution.get("successfulAction", "").strip()):
        return None
    return {"id": item["id"], "question": item["message"].strip(),
            "situation": "; ".join(state.get("symptoms") or []).strip(),
            "domain": (state.get("classification") or {}).get("domain") or "UNKNOWN",
            "root_cause": resolution["rootCause"].strip(),
            "successful_action": resolution["successfulAction"].strip(),
            "verified_at": resolution["verifiedAt"]}


def verified_cases() -> list[dict[str, str]]:
    """Hypothetical practice cases and unresolved questions never become labels."""
    return sorted((case for item in storage.list_all_incidents() if (case := _case(item))),
                  key=lambda case: case["id"])


def _document(case: dict[str, str]) -> dict[str, str]:
    content = (f"질문: {case['question']}\n상황: {case['situation']}\n"
               f"확인된 원인: {case['root_cause']}\n성공한 조치: {case['successful_action']}")
    return {"id": case["id"], "verification": "operator_verified", "text": content,
            "sha256": hashlib.sha256(content.encode()).hexdigest()}


def _distractors(oracle: dict[str, str], cases: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    candidates = [case for case in cases if case["id"] != oracle["id"]
                  and _split(case["question"]) == _split(oracle["question"])
                  and _normalized(case["question"]) != _normalized(oracle["question"])
                  and _normalized(case["root_cause"]) != _normalized(oracle["root_cause"])]
    if not candidates or limit < 1:
        return []
    scores = dict(rank(oracle["question"], [case["question"] + " " + case["situation"] for case in candidates]))
    score_by_id = {case["id"]: scores.get(index, 0) for index, case in enumerate(candidates)}
    candidates.sort(key=lambda case: (case["domain"] == oracle["domain"],
                                      score_by_id[case["id"]],
                                      case["id"]), reverse=True)
    return [_document(case) for case in candidates[:limit]]


def _split(question: str) -> str:
    # Identical normalized source questions stay in the same split.
    bucket = int(hashlib.sha256(_normalized(question).encode()).hexdigest()[:8], 16) % 10
    return "validation" if bucket == 0 else "train"


def examples(cases: list[dict[str, str]] | None = None, *, distractor_limit: int = 2,
             include_no_oracle: bool = True) -> list[dict[str, Any]]:
    cases = verified_cases() if cases is None else cases
    result: list[dict[str, Any]] = []
    for case in cases:
        oracle = _document(case)
        distractors = _distractors(case, cases, distractor_limit)
        for oracle_present in (True, False) if include_no_oracle and distractors else (True,):
            docs = ([oracle] if oracle_present else []) + distractors
            if oracle_present:
                answer = (f"확인된 원인: {case['root_cause']} [근거: {case['id']}]\n"
                          f"성공한 조치: {case['successful_action']} [근거: {case['id']}]"
                          "\n현재 장애에도 동일한지는 로그와 지표로 다시 확인해야 합니다.")
            else:
                answer = "제공된 문서에서 이 질문의 확인된 원인과 성공한 조치를 찾지 못했습니다. 운영자 확인이 필요합니다."
            question = case["question"] + (f"\n상황: {case['situation']}" if case["situation"] else "")
            user = {"question": question, "documents": docs,
                    "instruction": "확인된 근거만 사용해 원인과 조치를 간결하게 답하세요."}
            result.append({"messages": [{"role": "system", "content": SYSTEM},
                                        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                                        {"role": "assistant", "content": answer}],
                           "metadata": {"schema": SCHEMA_VERSION, "source_incident_id": case["id"],
                                        "oracle_document_id": case["id"] if oracle_present else None,
                                        "distractor_document_ids": [doc["id"] for doc in distractors],
                                        "variant": "oracle" if oracle_present else "no_oracle_abstain",
                                        "split": _split(case["question"]), "verified_at": case["verified_at"]}})
    return result


def status() -> dict[str, Any]:
    cases = verified_cases()
    items = examples(cases)
    return {"schema": SCHEMA_VERSION, "paper": "https://arxiv.org/abs/2403.10131",
            "verified_cases": len(cases), "training_examples": len(items),
            "train_examples": sum(item["metadata"]["split"] == "train" for item in items),
            "validation_examples": sum(item["metadata"]["split"] == "validation" for item in items),
            "mode": "dataset_only", "model_fine_tuned": False,
            "ready_for_fine_tuning": len(cases) >= 30 and any(item["metadata"]["split"] == "validation" for item in items),
            "requires_operator_review": True,
            "policy": "operator-verified incidents only; no-oracle examples abstain"}
