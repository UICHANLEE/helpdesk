"""Build reviewable, fictional HelpDesk questions from curated failure patterns."""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
PATTERNS = ROOT / "scenario_patterns.tsv"
OUTPUT = ROOT / "scenario_cases.tsv"
FIELDS = ("group", "domain", "question", "situation", "root_cause", "successful_action")

CORE_FRAMES = (
    ("{symptom} — 처음 접수한 문의입니다. 무엇부터 확인해야 하나요?",
     "사용자가 첫 문의를 남겼고 상세 로그는 운영자가 확인할 수 있다."),
    ("{symptom} — 같은 증상이 여러 요청에서 반복됩니다. 원인 후보를 어떻게 줄이나요?",
     "복수 요청에서 같은 증상이 관찰됐다."),
    ("{symptom} — Trace ID가 전달됐습니다. 어느 단계부터 조사해야 하나요?",
     "요청의 Trace ID를 통해 단계별 로그를 대조할 수 있다."),
    ("{symptom} — 운영 알림과 사용자 제보가 동시에 왔습니다. 무엇을 대조해야 하나요?",
     "운영 알림과 사용자 제보의 시각을 비교할 수 있다."),
    ("{symptom} — 임시 대응 뒤 다시 발생했습니다. 재발 원인을 어떻게 확인하나요?",
     "같은 증상이 재발했고 이전 조치의 효과는 확정되지 않았다."),
)
VARIANT_FRAMES = (
    "급해요. {symptom}. 지금 어떤 로그나 지표부터 봐야 하죠?",
    "이상해요, {symptom}. 다른 팀에 넘기기 전에 뭘 확인하면 되나요?",
)
UNCERTAIN_FRAMES = (
    "{symptom}이라는 말만 전달받았고 로그는 없습니다. 무엇을 더 물어봐야 하나요?",
    "사용자 제보: {symptom}. 재현 조건과 지표가 없는데 원인을 확정해도 되나요?",
)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def load_patterns(path: Path = PATTERNS) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    required = {"domain", "symptom", "evidence", "root_cause", "check", "successful_action"}
    if len(rows) != 100 or any(not required.issubset(row) or not all(row[key].strip() for key in required) for row in rows):
        raise ValueError("Expected 100 complete curated failure patterns")
    if len({_normalize(row["symptom"]) for row in rows}) != len(rows):
        raise ValueError("Failure pattern symptoms must be unique")
    return rows


def build_cases(patterns: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    patterns = load_patterns() if patterns is None else patterns
    cases: list[dict[str, str]] = []
    for pattern in patterns:
        symptom = pattern["symptom"]
        for frame, context in CORE_FRAMES:
            cases.append({"group": "scenario", "domain": pattern["domain"],
                          "question": frame.format(symptom=symptom),
                          "situation": f"가상 관찰: {pattern['evidence']}. {context}",
                          "root_cause": pattern["root_cause"],
                          "successful_action": pattern["successful_action"]})
        for frame in VARIANT_FRAMES:
            cases.append({"group": "variation", "domain": pattern["domain"],
                          "question": frame.format(symptom=symptom),
                          "situation": f"가상 관찰: {pattern['evidence']}. 문의 표현만 달라졌으며 원인은 검증되지 않았다.",
                          "root_cause": pattern["root_cause"],
                          "successful_action": pattern["successful_action"]})
        for frame in UNCERTAIN_FRAMES:
            cases.append({"group": "uncertain", "domain": pattern["domain"],
                          "question": frame.format(symptom=symptom),
                          "situation": "가상 접수: 오류 로그, 재현 조건, 점검 결과가 아직 전달되지 않았다.",
                          "root_cause": "정보 부족으로 원인 미확정",
                          "successful_action": f"원인을 단정하지 않고 {pattern['check']}에 필요한 로그와 시각을 요청"})
    expected = {"scenario": 500, "variation": 200, "uncertain": 200}
    if Counter(row["group"] for row in cases) != expected or len({_normalize(row["question"]) for row in cases}) != 900:
        raise ValueError("Generated scenario count or question uniqueness failed")
    return cases


def write_cases(path: Path = OUTPUT) -> dict[str, object]:
    cases = build_cases()
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(cases)
    return {"rows": len(cases), "groups": dict(Counter(row["group"] for row in cases)),
            "domains": dict(Counter(row["domain"] for row in cases)), "path": str(path)}


if __name__ == "__main__":
    import json
    print(json.dumps(write_cases(), ensure_ascii=False))
