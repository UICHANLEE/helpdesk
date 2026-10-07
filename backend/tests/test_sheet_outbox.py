from __future__ import annotations

import tempfile
import unittest
import asyncio
from pathlib import Path
from threading import Event
from unittest.mock import patch

from backend.main import sheet_delivery
from backend.models import IncidentState
from backend.sheets.snapshot import snapshot
from backend.storage import sqlite as storage


class SheetOutboxTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = storage.DB_PATH
        storage.DB_PATH = Path(self.temp.name) / "outbox.sqlite3"
        storage.init_db()

    def tearDown(self) -> None:
        storage.DB_PATH = self.old_path
        self.temp.cleanup()

    def test_question_answer_and_faq_enqueue_durable_updates(self) -> None:
        state = IncidentState(id="")
        incident_id = storage.create_incident("저장 실패", state)
        queue = storage.sheet_outbox_status()
        self.assertTrue(queue["pending"])
        self.assertEqual(queue["generation"], 1)
        storage.mark_sheet_synced(1)
        storage.save_state(state)
        self.assertFalse(storage.sheet_outbox_status()["pending"])
        state.diagnosis = "DB 쓰기 경로 오류"
        state.immediateActions = ["Save API 로그 확인"]
        storage.save_state(state)
        self.assertEqual(storage.sheet_outbox_status()["generation"], 2)
        self.assertEqual(snapshot()["tabs"][0]["rows"][0][6], "DB 쓰기 경로 오류")
        storage.mark_sheet_failed("temporary error")
        self.assertEqual(storage.sheet_outbox_status()["last_error"], "temporary error")
        storage.mark_sheet_synced(2)
        storage.save_faq("API:test", "왜 실패하나요?", "로그 확인")
        self.assertEqual(storage.sheet_outbox_status()["generation"], 3)
        example = IncidentState(id="", origin="example")
        storage.create_incident("연습 질문", example)
        self.assertEqual(storage.sheet_outbox_status()["generation"], 3)
        self.assertEqual(len(snapshot()["tabs"][0]["rows"]), 1)


if __name__ == "__main__":
    unittest.main()


class SheetDeliveryTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = storage.DB_PATH
        storage.DB_PATH = Path(self.temp.name) / "delivery.sqlite3"
        storage.init_db()

    async def asyncTearDown(self) -> None:
        storage.DB_PATH = self.old_path
        self.temp.cleanup()

    async def test_background_worker_uploads_queued_question(self) -> None:
        storage.create_incident("새 질문", IncidentState(id=""))
        completed = Event()

        def fake_sync() -> None:
            storage.mark_sheet_synced(storage.sheet_outbox_status()["generation"])
            completed.set()

        with patch("backend.main.sheets.status", return_value={"configured": True}), \
             patch("backend.main.sheets.sync_now", side_effect=fake_sync):
            task = asyncio.create_task(sheet_delivery())
            try:
                await asyncio.wait_for(asyncio.to_thread(completed.wait), timeout=3)
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        self.assertFalse(storage.sheet_outbox_status()["pending"])
