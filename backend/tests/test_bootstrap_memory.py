from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.knowledge import bootstrap, service, vector
from backend.raft import dataset
from backend.storage import sqlite as storage


class BootstrapMemoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.previous = storage.DB_PATH
        storage.DB_PATH = Path(self.temp.name) / "test.sqlite3"

    def tearDown(self) -> None:
        storage.DB_PATH = self.previous
        self.temp.cleanup()

    def test_training_indexes_patterns_without_promoting_them_to_verified_cases(self) -> None:
        storage.init_db()
        self.assertFalse(bootstrap.status()["active"])
        self.assertEqual(service.corpus_documents(), [])
        with patch.object(vector, "embed", side_effect=lambda texts, **kwargs: [[1.0, 0.0] for _ in texts]):
            trained = bootstrap.train()
            self.assertTrue(trained["active"])
            self.assertEqual(trained["patterns"], 100)
            self.assertEqual(trained["question_variants"], 900)
            self.assertEqual(trained["new_embeddings"], 100)
            found = service.search("DB 연결 수가 상한에 근접하는 현상", limit=3)
            self.assertTrue(any(item["id"].startswith("PATTERN-") for item in found))
            self.assertTrue(all(item["status"] == "synthetic" for item in found))
            self.assertEqual(bootstrap.train()["new_embeddings"], 0)
        self.assertEqual(dataset.verified_cases(), [])
        self.assertEqual(service.stats()["questions"], 0)
        self.assertEqual(service.stats()["resolved_knowledge"], 0)
        self.assertEqual(service.frequent_errors(), [])
        with patch.object(vector, "sync", side_effect=TimeoutError), \
             patch.object(vector, "scores", side_effect=AssertionError("dense search should be skipped")):
            fallback = service.search("DB 연결 수가 상한에 근접하는 현상", limit=1)
        self.assertEqual(fallback[0]["status"], "synthetic")
        self.assertEqual(fallback[0]["retrieval"], "lexical")

    def test_agent_search_downranks_unrelated_synthetic_domain(self) -> None:
        documents = [
            {"id": "PATTERN-001", "type": "pattern", "question": "모델 지연", "answer": "로드 지연",
             "actions": ["확인"], "status": "synthetic", "domain": "LLM", "content": "모델 지연"},
            {"id": "PATTERN-043", "type": "pattern", "question": "DB 연결", "answer": "연결 누수",
             "actions": ["확인"], "status": "synthetic", "domain": "DATABASE", "content": "DB 연결"},
        ]
        with patch.object(service, "corpus_documents", return_value=documents), \
             patch.object(vector, "sync", return_value=0), \
             patch.object(vector, "scores", return_value={"PATTERN-001": .9, "PATTERN-043": .8}), \
             patch.object(service, "rank", return_value=[(0, 1.0), (1, 1.0)]):
            rows = service.search("DB 연결", domain="DATABASE")
        self.assertEqual(rows[0]["id"], "PATTERN-043")
