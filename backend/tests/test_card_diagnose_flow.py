from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend.api.diagnose import diagnose
from backend.api.incidents import create_card, update_status
from backend.models import CardCreateRequest, DiagnoseRequest, IncidentStatus, StatusUpdateRequest
from backend.reports import daily
from backend.sheets.snapshot import snapshot
from backend.storage import sqlite as storage


class CardDiagnoseFlowTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = storage.DB_PATH
        storage.DB_PATH = Path(self.temp.name) / "cards.sqlite3"
        storage.init_db()

    async def asyncTearDown(self) -> None:
        storage.DB_PATH = self.old_path
        self.temp.cleanup()

    async def test_card_is_not_a_question_until_diagnose_submits_it(self) -> None:
        card = await create_card(CardCreateRequest(title="모델 지연 점검"))
        incident_id = card["id"]
        self.assertEqual(card["message"], "")
        self.assertEqual(card["state"]["workflowStage"], "todo")
        self.assertEqual(storage.list_knowledge(), [])
        self.assertEqual(snapshot()["tabs"][0]["rows"], [])
        self.assertFalse(storage.sheet_outbox_status()["pending"])
        with self.assertRaises(HTTPException):
            await update_status(incident_id, StatusUpdateRequest(status=IncidentStatus.resolved,
                               root_cause="원인", successful_action="조치"))

        parsed = {"text": "점심 이후 모델 응답이 느려요", "signals": [], "http_status": None,
                  "error_type": None, "endpoint": None, "pod": None}
        judgment = {"primary": "LLM", "secondary": None, "severity": "P3", "depth": "MEDIUM",
                    "source": "rules", "confidence": None}
        with patch("backend.agent.orchestrator.classify", new_callable=AsyncMock, return_value=(parsed, judgment)), \
             patch("backend.agent.orchestrator.qwen_model_available", return_value=False), \
             patch("backend.agent.orchestrator.investigate", new_callable=AsyncMock):
            result = await diagnose(DiagnoseRequest(incident_id=incident_id, message=parsed["text"]))
            await asyncio.sleep(0)
        self.assertEqual(result.incident_id, incident_id)
        record = storage.get_incident(incident_id)
        self.assertEqual(record["message"], parsed["text"])
        self.assertEqual(record["state"]["title"], "모델 지연 점검")
        self.assertEqual(record["state"]["workflowStage"], "in_progress")
        self.assertIsNotNone(record["state"]["questionSubmittedAt"])
        self.assertEqual(snapshot()["tabs"][0]["rows"][0][3], parsed["text"])
        self.assertEqual(daily.report(daily._day(record["state"]["questionSubmittedAt"]))["questions"], 1)
        self.assertTrue(storage.sheet_outbox_status()["pending"])
        with self.assertRaises(HTTPException):
            await diagnose(DiagnoseRequest(incident_id=incident_id, message="중복 질문"))


if __name__ == "__main__":
    unittest.main()
