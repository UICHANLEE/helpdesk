"""Stable, keyed rows for the SMC-Helpdesk Google Sheet.

Run ``.venv/bin/python -m backend.sheets.snapshot`` from the repository root.
The output is JSON. It contains local records only and never includes API keys.
"""

from __future__ import annotations

import json
from datetime import datetime

from backend.reports import daily
from backend.storage import sqlite as storage

SPREADSHEET_ID = "1DxtdDGSBx5L8FbHWsd8hATeQj24_Wyfd_GG1dNuf21E"

INCIDENT_HEADERS = [
    "날짜(KST)", "시각(KST)", "Incident ID", "질문", "상황", "영역", "진단",
    "제안된 조치", "다음 조치", "조치 이력", "확인된 원인", "성공한 조치",
    "상태", "최종 수정(UTC)",
]
SUMMARY_HEADERS = ["날짜(KST)", "업무 요약", "질문 수", "해결 수", "주요 영역"]
FAQ_HEADERS = ["FAQ ID", "오류 유형", "질문", "답변", "최종 수정(UTC)"]


def snapshot() -> dict:
    incidents = storage.list_all_incidents()
    incident_rows: list[list[str]] = []
    for item in incidents:
        created = datetime.fromisoformat(item["created_at"]).astimezone(daily.KST)
        state = item["state"]
        resolution = state.get("resolution") or {}
        incident_rows.append([
            created.date().isoformat(), created.strftime("%H:%M:%S"), item["id"],
            item["message"], "; ".join(state.get("symptoms", [])),
            (state.get("classification") or {}).get("domain", "UNKNOWN"),
            state.get("diagnosis", ""), "; ".join(state.get("immediateActions", [])),
            state.get("recommendedAction", ""),
            "; ".join(f"{action.get('label', '')} [{action.get('status', 'proposed')}]"
                      for action in state.get("actions", [])),
            resolution.get("rootCause", ""), resolution.get("successfulAction", ""),
            state.get("status", "new"), item["updated_at"],
        ])

    days = sorted({row[0] for row in incident_rows})
    summary_rows: list[list[str]] = []
    for day in days:
        result = daily.report(day, incidents)
        domains = ", ".join(f"{name} {count}건" for name, count in result["domains"].items())
        summary_rows.append([day, result["summary"], str(result["questions"]),
                             str(result["resolved"]), domains])

    faq_rows = [[str(item["id"]), item["signature"], item["question"],
                 item["answer"], item["updated_at"]] for item in storage.list_faq()]
    return {"spreadsheet_id": SPREADSHEET_ID, "tabs": [
        {"name": "질문 로그", "key_column": "C", "headers": INCIDENT_HEADERS, "rows": incident_rows},
        {"name": "일별 요약", "key_column": "A", "headers": SUMMARY_HEADERS, "rows": summary_rows},
        {"name": "FAQ", "key_column": "A", "headers": FAQ_HEADERS, "rows": faq_rows},
    ]}


if __name__ == "__main__":
    print(json.dumps(snapshot(), ensure_ascii=False))
