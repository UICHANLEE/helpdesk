from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

from fastapi import HTTPException

from backend.api.incidents import update_status
from backend.api.knowledge import FaqRequest, publish_faq
from backend.knowledge.service import search
from backend.models import Classification, IncidentState, IncidentStatus, StatusUpdateRequest
from backend.reports import daily
from backend.storage import backup, sqlite as storage


class KnowledgeWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = storage.DB_PATH
        self.old_reports = daily.REPORT_DIR
        self.old_backups = backup.BACKUP_DIR
        storage.DB_PATH = Path(self.temp.name) / "incidents.sqlite3"
        daily.REPORT_DIR = Path(self.temp.name) / "reports"
        backup.BACKUP_DIR = Path(self.temp.name) / "backups"
        storage.init_db()

    def tearDown(self) -> None:
        storage.DB_PATH = self.old_path
        daily.REPORT_DIR = self.old_reports
        backup.BACKUP_DIR = self.old_backups
        self.temp.cleanup()

    def test_only_verified_resolution_enters_retrieval_and_daily_workbook(self) -> None:
        state = IncidentState(id="", classification=Classification(domain="DATABASE"),
                              symptoms=["저장 API HTTP 500"], diagnosis="추정 원인", immediateActions=["제안된 조치"])
        incident_id = storage.create_incident("DB 저장 실패", state)
        self.assertEqual(search("DB 저장 실패"), [])
        with self.assertRaises(HTTPException):
            asyncio.run(update_status(incident_id, StatusUpdateRequest(status=IncidentStatus.resolved)))
        changed_since = datetime.now(timezone.utc)
        asyncio.run(update_status(incident_id, StatusUpdateRequest(status=IncidentStatus.resolved,
                           root_cause="연결 풀 고갈", successful_action="연결 누수 수정")))
        self.assertEqual(search("DB 저장 실패")[0]["answer"], "연결 풀 고갈")
        self.assertEqual(publish_faq(FaqRequest(incident_id=incident_id, question="저장 실패 시?",
                                              answer="연결 풀을 확인합니다."))["question"], "저장 실패 시?")
        day = daily.available_days()[0]
        daily.refresh_all(changed_since)
        workbook = daily.REPORT_DIR / f"{day}.xlsx"
        with ZipFile(workbook) as archive:
            self.assertIn("연결 누수 수정", archive.read("xl/worksheets/sheet2.xml").decode())
        snapshot = backup.backup_now()
        self.assertEqual(snapshot["backup_count"], 1)
        with closing(sqlite3.connect(backup.BACKUP_DIR / snapshot["latest_backup"])) as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM incidents").fetchone()[0], 1)
            self.assertEqual(database.execute("PRAGMA integrity_check").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
