from __future__ import annotations

import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from backend.api.knowledge import FaqRequest, publish_faq
from backend.api.incidents import review_example
from backend.agent.orchestrator import rehearse_example
from backend.knowledge.seed_examples import load_cases, seed_examples
from backend.knowledge.service import corpus_documents, frequent_errors, stats
from backend.observability.trace import graph
from backend.reports import daily
from backend.sheets.snapshot import snapshot
from backend.storage import sqlite as storage
from backend.models import ExampleReviewRequest


class ExampleSeedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = storage.DB_PATH
        storage.DB_PATH = Path(self.temp.name) / "examples.sqlite3"

    def tearDown(self) -> None:
        storage.DB_PATH = self.old_path
        self.temp.cleanup()

    def test_100_examples_are_idempotent_and_excluded_from_operational_reporting(self) -> None:
        self.assertEqual(len(load_cases()), 100)
        first = seed_examples(index_vectors=False)
        self.assertEqual(first["created"], 100)
        self.assertEqual(seed_examples(index_vectors=False)["created"], 0)
        examples = storage.list_incidents("examples")
        self.assertEqual(len(examples), 100)
        self.assertEqual(storage.list_incidents(), [])
        self.assertEqual(stats()["example_count"], 100)
        self.assertEqual(stats()["resolved_knowledge"], 0)
        self.assertEqual(len(corpus_documents()), 0)
        self.assertEqual(frequent_errors(), [])
        self.assertEqual(len({item["message"] for item in examples}), 100)
        sample = examples[0]
        self.assertEqual(sample["state"]["status"], "new")
        self.assertEqual(sample["state"]["examplePhase"], "seeded")
        self.assertIsNone(sample["state"]["resolution"])
        self.assertTrue(sample["state"]["exampleReference"]["rootCause"])
        self.assertEqual([event["type"] for event in storage.get_events(sample["id"])], ["example_seeded"])
        trace = graph(sample, storage.get_events(sample["id"]))
        self.assertEqual(trace["evidence"], [])
        day = datetime.fromisoformat(sample["created_at"]).astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()
        self.assertEqual(daily.report(day)["questions"], 0)
        self.assertEqual(snapshot()["tabs"][0]["rows"], [])
        with self.assertRaises(HTTPException):
            publish_faq(FaqRequest(incident_id=sample["id"], question="예시 FAQ?", answer="가상 조치"))


if __name__ == "__main__":
    unittest.main()


class ExampleRehearsalTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = storage.DB_PATH
        storage.DB_PATH = Path(self.temp.name) / "rehearsal.sqlite3"
        seed_examples(index_vectors=False)

    async def asyncTearDown(self) -> None:
        storage.DB_PATH = self.old_path
        self.temp.cleanup()

    async def test_first_diagnosis_is_recorded_before_reference_correction(self) -> None:
        incident_id = storage.list_incidents("examples")[-1]["id"]
        self.assertEqual(corpus_documents(), [])
        from incident import parse_incident, rule_judgment
        message = storage.get_incident(incident_id)["message"]
        parsed = parse_incident(message)
        judgment = rule_judgment(parsed)
        with patch("backend.agent.orchestrator.classify", new=AsyncMock(return_value=(parsed, judgment))) as classify_mock, \
             patch("backend.agent.orchestrator.qwen_model_available", return_value=True), \
             patch("backend.agent.orchestrator.retrieve", new=AsyncMock(return_value=[])), \
             patch("backend.agent.orchestrator.tools_for", return_value=[]), \
             patch("backend.agent.orchestrator.qwen_diagnose", new=AsyncMock(return_value={
                 "diagnosis": "첫 추정 원인", "immediate_actions": ["첫 점검 제안"],
                 "recommended_action": "첫 점검 제안", "hypotheses": []})):
            _, task = await rehearse_example(incident_id)
            await task
        self.assertIn("상황:", classify_mock.await_args.args[0])
        draft = storage.get_incident(incident_id)["state"]
        self.assertEqual(draft["examplePhase"], "awaiting_review")
        self.assertEqual(draft["firstDiagnosis"], "첫 추정 원인")
        self.assertEqual(corpus_documents(), [])
        reference = draft["exampleReference"]
        await review_example(incident_id, ExampleReviewRequest(
            root_cause=reference["rootCause"], successful_action=reference["successfulAction"],
            note="참고 답안과 비교"))
        reviewed = storage.get_incident(incident_id)["state"]
        self.assertEqual(reviewed["examplePhase"], "reviewed")
        self.assertEqual(reviewed["firstDiagnosis"], "첫 추정 원인")
        self.assertEqual(reviewed["diagnosis"], reference["rootCause"])
        self.assertEqual(reviewed["resolution"]["reviewSource"], "operator")
        self.assertEqual(len(corpus_documents()), 1)
        types = [event["type"] for event in storage.get_events(incident_id)]
        self.assertEqual(types, ["example_seeded", "rehearsal_started", "user", "jev", "retrieval", "reasoning_started", "reasoning", "action", "example_reviewed"])
