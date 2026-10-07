from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from backend.api.knowledge import FaqRequest, publish_faq
from backend.knowledge.seed_examples import load_cases, seed_examples
from backend.knowledge.service import corpus_documents, frequent_errors, stats
from backend.observability.trace import graph
from backend.reports import daily
from backend.sheets.snapshot import snapshot
from backend.storage import sqlite as storage


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
        self.assertEqual(sum(item["status"] == "example" for item in corpus_documents()), 100)
        self.assertEqual(frequent_errors(), [])
        self.assertEqual(len({item["message"] for item in examples}), 100)
        sample = examples[0]
        self.assertEqual(sample["state"]["status"], "resolved")
        self.assertEqual(sample["state"]["claims"][0]["verification"], "example")
        self.assertTrue(sample["state"]["resolution"]["rootCause"])
        self.assertTrue(sample["state"]["resolution"]["successfulAction"])
        self.assertEqual([event["type"] for event in storage.get_events(sample["id"])], ["user", "status_changed"])
        trace = graph(sample, storage.get_events(sample["id"]))
        self.assertIn("example", {item["status"] for item in trace["evidence"]})
        day = datetime.fromisoformat(sample["created_at"]).astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()
        self.assertEqual(daily.report(day)["questions"], 0)
        self.assertEqual(snapshot()["tabs"][0]["rows"], [])
        with self.assertRaises(HTTPException):
            publish_faq(FaqRequest(incident_id=sample["id"], question="예시 FAQ?", answer="가상 조치"))


if __name__ == "__main__":
    unittest.main()
