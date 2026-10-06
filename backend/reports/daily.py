"""KST daily activity summaries and dependency-free Excel exports."""

from __future__ import annotations

import os
import re
import zipfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from backend.storage import sqlite as storage

KST = ZoneInfo("Asia/Seoul")
REPORT_DIR = Path(os.getenv("RAFT_REPORT_DIR", str(Path(__file__).parent / "data")))


def _day(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp).astimezone(KST).date().isoformat()


def report(day: str) -> dict:
    date.fromisoformat(day)
    incidents = [item for item in storage.list_all_incidents() if _day(item["created_at"]) == day]
    records = []
    for item in incidents:
        state = item["state"]
        records.append({"time": datetime.fromisoformat(item["created_at"]).astimezone(KST).strftime("%H:%M:%S"),
                        "incident_id": item["id"], "question": item["message"],
                        "situation": "; ".join(state.get("symptoms", [])),
                        "domain": (state.get("classification") or {}).get("domain", "UNKNOWN"),
                        "diagnosis": state.get("diagnosis", ""),
                        "actions": "; ".join(state.get("immediateActions", [])),
                        "recommended_action": state.get("recommendedAction", ""),
                        "action_history": "; ".join(f"{action.get('label', '')} [{action.get('status', 'proposed')}]" for action in state.get("actions", [])),
                        "verified_cause": (state.get("resolution") or {}).get("rootCause", ""),
                        "successful_action": (state.get("resolution") or {}).get("successfulAction", ""),
                        "status": state.get("status", "new")})
    domains = Counter(row["domain"] for row in records)
    resolved = sum(row["status"] == "resolved" for row in records)
    action_count = sum(bool(row["actions"]) for row in records)
    top = domains.most_common(3)
    summary = (f"{day}에는 질문 {len(records)}건을 기록했고 {resolved}건을 해결했습니다. "
               f"주요 영역: {', '.join(f'{name} {count}건' for name, count in top) or '없음'}. "
               f"조치 제안이 기록된 건은 {action_count}건입니다.")
    return {"date": day, "summary": summary, "questions": len(records), "resolved": resolved,
            "domains": dict(domains), "records": records}


def available_days() -> list[str]:
    return sorted({_day(item["created_at"]) for item in storage.list_all_incidents()}, reverse=True)


def _column(number: int) -> str:
    result = ""
    while number:
        number, rem = divmod(number - 1, 26)
        result = chr(65 + rem) + result
    return result


def _sheet(rows: list[list[str]], widths: list[int]) -> bytes:
    lines = []
    for row_number, row in enumerate(rows, 1):
        cells = []
        for col_number, value in enumerate(row, 1):
            # Inline strings prevent a user question beginning with '=' from becoming a formula.
            safe = escape(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value)))
            cells.append(f'<c r="{_column(col_number)}{row_number}" s="{1 if row_number == 1 else 2}" t="inlineStr"><is><t xml:space="preserve">{safe}</t></is></c>')
        lines.append(f'<row r="{row_number}" ht="{27 if row_number == 1 else 38}" customHeight="1">{"".join(cells)}</row>')
    columns = "".join(f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>' for index, width in enumerate(widths, 1))
    extent = f"A1:{_column(max(len(row) for row in rows))}{len(rows)}"
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<dimension ref="{extent}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{columns}</cols>'
            f'<sheetData>{"".join(lines)}</sheetData></worksheet>').encode()


def export(day: str) -> Path:
    data = report(day)
    REPORT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    REPORT_DIR.chmod(0o700)
    path = REPORT_DIR / f"{day}.xlsx"
    temporary = path.with_suffix(".tmp")
    headers = ["시각(KST)", "Incident", "질문", "상황", "영역", "진단", "제안된 조치", "다음 조치", "조치 결정 이력", "확인된 원인", "실제 성공한 조치", "상태"]
    log_rows = [headers] + [[str(row[key]) for key in ("time", "incident_id", "question", "situation", "domain", "diagnosis", "actions", "recommended_action", "action_history", "verified_cause", "successful_action", "status")] for row in data["records"]]
    summary_rows = [["날짜", day], ["업무 요약", data["summary"]], ["질문 수", str(data["questions"])],
                    ["해결 수", str(data["resolved"])], ["영역", "건수"]]
    summary_rows += [[name, str(count)] for name, count in data["domains"].items()]
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as book:
        book.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        book.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        book.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="업무 요약" sheetId="1" r:id="rId1"/><sheet name="질문 로그" sheetId="2" r:id="rId2"/></sheets></workbook>')
        book.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        book.writestr("xl/styles.xml", '<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Aptos"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Aptos"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF262635"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="1" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        book.writestr("xl/worksheets/sheet1.xml", _sheet(summary_rows, [20, 90]))
        book.writestr("xl/worksheets/sheet2.xml", _sheet(log_rows, [14, 16, 70, 55, 20, 55, 70, 55, 55, 55, 55, 18]))
    temporary.replace(path)
    path.chmod(0o600)
    return path


def refresh_all() -> None:
    for day in available_days():
        export(day)
