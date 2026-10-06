from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from fastapi import HTTPException

from backend.api.incidents import update_status
from backend.api.knowledge import FaqRequest, publish_faq
from backend.knowledge.service import search
from backend.models import Classification, IncidentState, IncidentStatus, StatusUpdateRequest
from backend.reports import daily
from backend.storage import sqlite as storage


class KnowledgeWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = storage.DB_PATH
        self.old_reports = daily.REPORT_DIR
        storage.DB_PATH = Path(self.temp.name) / "incidents.sqlite3"
        daily.REPORT_DIR = Path(self.temp.name) / "reports"
        storage.init_db()

    def tearDown(self) -> None:
        storage.DB_PATH = self.old_path
        daily.REPORT_DIR = self.old_reports
        self.temp.cleanup()

    def test_only_verified_resolution_enters_retrieval_and_daily_workbook(self) -> None:
        state = IncidentState(id="", classification=Classification(domain="DATABASE"),
                              symptoms=["저장 API HTTP 500"], diagnosis="추정 원인", immediateActions=["제안된 조치"])
        incident_id = storage.create_incident("DB 저장 실패", state)
        self.assertEqual(search("DB 저장 실패"), [])
        with self.assertRaises(HTTPException):
            asyncio.run(update_status(incident_id, StatusUpdateRequest(status=IncidentStatus.resolved)))
        asyncio.run(update_status(incident_id, StatusUpdateRequest(status=IncidentStatus.resolved,
                           root_cause="연결 풀 고갈", successful_action="연결 누수 수정")))
        self.assertEqual(search("DB 저장 실패")[0]["answer"], "연결 풀 고갈")
        self.assertEqual(publish_faq(FaqRequest(incident_id=incident_id, question="저장 실패 시?",
                                              answer="연결 풀을 확인합니다."))["question"], "저장 실패 시?")
        day = daily.available_days()[0]
        workbook = daily.export(day)
        with ZipFile(workbook) as archive:
            self.assertIn("연결 누수 수정", archive.read("xl/worksheets/sheet2.xml").decode())
        self.assertGreaterEqual(len(storage.pending_sync()), 3)


if __name__ == "__main__":
    unittest.main()
