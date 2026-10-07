"""Grounded next checks when the reasoning model does not return an answer."""

from __future__ import annotations

from typing import Any


def from_verified_history(matches: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Use a close verified case as a lead, never as proof of this incident's cause."""
    if not matches:
        return None
    best_score = max(float(item.get("score") or 0) for item in matches)
    candidates = [item for item in matches if item.get("verification") == "verified" and
                  float(item.get("score") or 0) >= (0.25 if item.get("retrieval") == "hybrid" else 0.08) and
                  float(item.get("score") or 0) >= best_score * 0.8 and item.get("title")]
    if not candidates:
        return None
    match = max(candidates, key=lambda item: float(item.get("score") or 0))
    case_id = str(match["id"])
    historical_cause = str(match["title"]).strip()
    check = f"{case_id}의 당시 증상·원인과 현재 로그·지표를 비교해 같은 문제인지 확인"
    return {
        "diagnosis": f"유사 해결 기록 {case_id}: {historical_cause} (현재 원인은 미확인)",
        "immediate_actions": [check],
        "recommended_action": check,
        "hypotheses": [{"name": historical_cause, "rationale": f"{case_id}의 확인된 해결 기록과 증상이 유사하나 현재 건은 검증 전"}],
        "historical_case_id": case_id,
    }
