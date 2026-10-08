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


def from_synthetic_pattern(matches: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Offer a read-only hypothesis when Qwen fails and a close fictional pattern exists."""
    if not matches:
        return None
    best_score = max(float(item.get("score") or 0) for item in matches)
    candidates = [item for item in matches if item.get("verification") == "synthetic"
                  and str(item.get("id", "")).startswith("PATTERN-")
                  and float(item.get("score") or 0) >= .55
                  and float(item.get("score") or 0) >= best_score * .9
                  and item.get("title")]
    if not candidates:
        return None
    match = max(candidates, key=lambda item: float(item.get("score") or 0))
    pattern_id = str(match["id"])
    cause = str(match["title"]).strip()
    summary = str(match.get("summary") or "")
    check = summary.rpartition("| 확인:")[2].strip() or "관련 로그와 지표를 확인해 가상 패턴이 현재 상황과 일치하는지 검증"
    return {
        "diagnosis": f"가상 패턴 {pattern_id} 참고: {cause} 가능성 (현재 원인 미확인)",
        "immediate_actions": [check], "recommended_action": check,
        "hypotheses": [{"name": cause, "rationale": f"{pattern_id}은 가상 패턴이며 현재 장애의 확인 근거가 아님"}],
        "synthetic_pattern_id": pattern_id,
    }
