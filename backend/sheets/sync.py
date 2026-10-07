"""Explicit, idempotent upload from local SQLite to one Google Sheet."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any
from urllib.parse import quote

from backend.sheets.snapshot import SPREADSHEET_ID, snapshot
from backend.storage import sqlite as storage

SCOPE = "https://www.googleapis.com/auth/spreadsheets"
BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
_sync_lock = threading.Lock()


class SheetSyncError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def credential_file() -> Path:
    configured = os.getenv("RAFT_GOOGLE_SERVICE_ACCOUNT_FILE")
    return Path(configured).expanduser() if configured else Path(__file__).resolve().parents[2] / "secrets" / "google-service-account.json"


def status() -> dict[str, Any]:
    path = credential_file()
    email = None
    if path.is_file():
        try:
            data = json.loads(path.read_text())
            if data.get("type") == "service_account":
                email = data.get("client_email")
        except (OSError, ValueError):
            pass
    return {"configured": bool(email), "service_account_email": email,
            "credential_path": str(path), "sheet_url": SHEET_URL,
            "last_sync": storage.get_sheet_sync(), "queue": storage.sheet_outbox_status()}


def _rows(values: list[list[Any]], headers: list[str], key_column: str) -> tuple[dict[str, tuple[int, list[str]]], int]:
    if values and [str(cell) for cell in values[0][:len(headers)]] != headers:
        raise SheetSyncError("Google Sheet의 열 제목이 로컬 기록과 다릅니다. 시트 구성을 확인하세요.", 409)
    key_index = ord(key_column) - ord("A")
    keyed: dict[str, tuple[int, list[str]]] = {}
    for row_number, row in enumerate(values[1:], 2):
        key = str(row[key_index]).strip() if len(row) > key_index else ""
        if not key:
            continue
        if key in keyed:
            raise SheetSyncError(f"Google Sheet에 중복된 키가 있습니다: {key}", 409)
        keyed[key] = (row_number, [str(cell) for cell in row])
    return keyed, max(1, len(values))


def plan(data: dict[str, Any], current: dict[str, list[list[Any]]], properties: dict[str, dict[str, int]]) -> dict[str, Any]:
    """Return only changed rows. RAW input keeps question text from becoming formulas."""
    writes: list[dict[str, Any]] = []
    expansions: list[dict[str, Any]] = []
    counts = {"updated_rows": 0, "inserted_rows": 0, "unchanged_rows": 0}
    for tab in data["tabs"]:
        name, headers = tab["name"], tab["headers"]
        if name not in properties:
            raise SheetSyncError(f"Google Sheet 탭을 찾을 수 없습니다: {name}", 409)
        values = current.get(name, [])
        keyed, last_row = _rows(values, headers, tab["key_column"])
        if not values:
            writes.append({"range": f"'{name}'!A1:{chr(64 + len(headers))}1", "values": [headers]})
        key_index = ord(tab["key_column"]) - ord("A")
        seen: set[str] = set()
        for row in tab["rows"]:
            row = [str(value if value is not None else "") for value in row]
            if len(row) != len(headers):
                raise SheetSyncError(f"로컬 기록의 열 개수가 맞지 않습니다: {name}", 500)
            key = row[key_index].strip()
            if not key or key in seen:
                raise SheetSyncError(f"로컬 기록의 고유 키가 비어 있거나 중복되었습니다: {name}", 500)
            seen.add(key)
            if key in keyed:
                row_number, existing = keyed[key]
                if (existing + [""] * len(headers))[:len(headers)] == row:
                    counts["unchanged_rows"] += 1
                    continue
                counts["updated_rows"] += 1
            else:
                last_row += 1
                row_number = last_row
                counts["inserted_rows"] += 1
            writes.append({"range": f"'{name}'!A{row_number}:{chr(64 + len(headers))}{row_number}", "values": [row]})
        row_count = properties[name]["rowCount"]
        if last_row > row_count:
            expansions.append({"appendDimension": {"sheetId": properties[name]["sheetId"],
                                                    "dimension": "ROWS", "length": last_row - row_count}})
    return {"writes": writes, "expansions": expansions, **counts}


def _request_json(session: Any, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    from google.auth.exceptions import GoogleAuthError
    from requests.exceptions import RequestException

    try:
        response = session.request(method, url, timeout=20, **kwargs)
        response.raise_for_status()
        return response.json()
    except RequestException as error:
        code = getattr(getattr(error, "response", None), "status_code", None)
        if code in (401, 403):
            raise SheetSyncError("Google Sheet 편집 권한 또는 서비스 계정 인증을 확인하세요.", 403) from error
        if code == 404:
            raise SheetSyncError("Google Sheet를 찾을 수 없습니다.", 404) from error
        raise SheetSyncError("Google Sheets 연결에 실패했습니다. 잠시 후 다시 시도하세요.") from error
    except GoogleAuthError as error:
        raise SheetSyncError("Google 서비스 계정 인증에 실패했습니다.", 403) from error
    except ValueError as error:
        raise SheetSyncError("Google Sheets 응답을 읽지 못했습니다.") from error


def sync_now() -> dict[str, Any]:
    if not _sync_lock.acquire(blocking=False):
        raise SheetSyncError("이미 Google Sheet에 업로드 중입니다.", 409)
    try:
        path = credential_file()
        if not status()["configured"]:
            raise SheetSyncError("Google 서비스 계정 연결이 필요합니다. 설정 안내를 확인하세요.", 503)
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import AuthorizedSession
            from google.auth.exceptions import GoogleAuthError
        except ImportError as error:
            raise SheetSyncError("Google 인증 패키지를 설치해야 합니다.", 503) from error
        try:
            credentials = service_account.Credentials.from_service_account_file(str(path), scopes=[SCOPE])
            session = AuthorizedSession(credentials)
        except (OSError, ValueError, GoogleAuthError) as error:
            raise SheetSyncError("Google 인증 설정을 읽지 못했습니다. 서비스 계정 파일과 설치 상태를 확인하세요.", 503) from error

        generation = storage.sheet_outbox_status()["generation"]
        data = snapshot()
        metadata = _request_json(session, "GET", f"{BASE_URL}/{SPREADSHEET_ID}",
                                 params={"fields": "sheets(properties(sheetId,title,gridProperties(rowCount)))"})
        properties = {item["properties"]["title"]: {
            "sheetId": item["properties"]["sheetId"],
            "rowCount": item["properties"]["gridProperties"]["rowCount"],
        } for item in metadata.get("sheets", [])}
        current = {}
        ranges = {}
        for tab in data["tabs"]:
            name = tab["name"]
            if name not in properties:
                raise SheetSyncError(f"Google Sheet 탭을 찾을 수 없습니다: {name}", 409)
            last_col = chr(64 + len(tab["headers"]))
            sheet_range = f"'{name}'!A1:{last_col}"
            ranges[name] = sheet_range
            result = _request_json(session, "GET", f"{BASE_URL}/{SPREADSHEET_ID}/values/{quote(sheet_range, safe='')}",
                                   params={"valueRenderOption": "UNFORMATTED_VALUE"})
            current[name] = result.get("values", [])

        changes = plan(data, current, properties)
        if changes["expansions"]:
            _request_json(session, "POST", f"{BASE_URL}/{SPREADSHEET_ID}:batchUpdate",
                          json={"requests": changes["expansions"]})
        if changes["writes"]:
            _request_json(session, "POST", f"{BASE_URL}/{SPREADSHEET_ID}/values:batchUpdate",
                          json={"valueInputOption": "RAW", "data": changes["writes"]})
            verified = {}
            for name, sheet_range in ranges.items():
                result = _request_json(session, "GET", f"{BASE_URL}/{SPREADSHEET_ID}/values/{quote(sheet_range, safe='')}",
                                       params={"valueRenderOption": "UNFORMATTED_VALUE"})
                verified[name] = result.get("values", [])
            remaining = plan(data, verified, properties)
            if remaining["writes"]:
                raise SheetSyncError("업로드 후 검증에서 일부 행이 일치하지 않았습니다. 다시 업로드하세요.")
        saved = storage.record_sheet_sync(changes["updated_rows"], changes["inserted_rows"], changes["unchanged_rows"])
        storage.mark_sheet_synced(generation)
        return {**saved, "sheet_url": SHEET_URL}
    finally:
        _sync_lock.release()
