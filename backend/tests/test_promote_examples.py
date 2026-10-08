from __future__ import annotations

import tempfile
import asyncio
import unittest
from pathlib import Path

from backend.knowledge import promote_examples, service
from backend.api.incidents import review_example
from backend.knowledge.seed_examples import seed_examples
from backend.raft import dataset
from backend.reports import daily
from backend.sheets.snapshot import snapshot
from backend.storage import sqlite as storage
from backend.models import ExampleReviewRequest


class PromoteExamplesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = storage.DB_PATH
        storage.DB_PATH = Path(self.temp.name) / "examples.sqlite3"

    def tearDown(self) -> None:
        storage.DB_PATH = self.old_path
        self.temp.cleanup()

    def test_prepared_resolutions_feed_raft_without_becoming_live_incidents(self) -> None:
        seed_examples(index_vectors=False)
        first = promote_examples.promote(index_vectors=False)
        self.assertEqual(first["promoted"], 1000)
        self.assertEqual(promote_examples.promote(index_vectors=False)["promoted"], 0)
        incident = storage.list_incidents("examples")[0]
        state = incident["state"]
        self.assertEqual(state["examplePhase"], "preloaded")
        self.assertEqual(state["status"], "resolved")
        self.assertEqual(state["workflowStage"], "done")
        self.assertEqual(state["resolution"]["verification"], "hypothetical_reference")
        self.assertNotIn("verifiedAt", state["resolution"])
        self.assertEqual(service.stats()["example_preloaded"], 1000)
        self.assertEqual(len(dataset.synthetic_cases()), 1000)
        self.assertEqual(len(dataset.verified_cases()), 0)
        self.assertEqual(len(service.corpus_documents()), 100)
        samples = dataset.synthetic_examples()
        self.assertGreaterEqual(len(samples), 1000)
        self.assertEqual(storage.list_incidents(), [])
        self.assertEqual(snapshot()["tabs"][0]["rows"], [])
        self.assertEqual(daily.report("2026-10-08")["questions"], 0)

        positive = next(row for row in samples
                        if row["metadata"]["variant"] == "oracle")
        self.assertEqual(positive["metadata"]["provenance"], "synthetic_reference")
        self.assertIn("가상 사례의 원인 가정", positive["messages"][2]["content"])
        families = {}
        for row in samples:
            family = row["metadata"]["source_family"]
            families.setdefault(family, set()).add(row["metadata"]["split"])
        self.assertTrue(all(len(splits) == 1 for splits in families.values()))

        revised = asyncio.run(review_example(incident["id"], ExampleReviewRequest(
            root_cause="운영자 수정 원인", successful_action="운영자 수정 조치", note="예시 수정")))
        self.assertEqual(revised["examplePhase"], "reviewed")
        self.assertEqual(revised["resolution"]["verification"], "hypothetical_reference")
        self.assertEqual(storage.get_incident(incident["id"])["state"]["resolution"]["rootCause"], "운영자 수정 원인")


if __name__ == "__main__":
    unittest.main()
