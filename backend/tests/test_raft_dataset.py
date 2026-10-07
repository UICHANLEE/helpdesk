from __future__ import annotations

import json
import asyncio
import tempfile
import unittest
from pathlib import Path

from backend.models import Classification, IncidentState, IncidentStatus
from backend.api.knowledge import download_raft_dataset, raft_dataset_status
from backend.raft import dataset
from backend.storage import sqlite as storage


class RaftDatasetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = storage.DB_PATH
        storage.DB_PATH = Path(self.temp.name) / "raft.sqlite3"
        storage.init_db()

    def tearDown(self) -> None:
        storage.DB_PATH = self.old_path
        self.temp.cleanup()

    def _incident(self, question: str, cause: str, action: str, *, origin: str = "live",
                  resolved: bool = True) -> str:
        state = IncidentState(id="", origin=origin, classification=Classification(domain="DATABASE"),
                              status=IncidentStatus.resolved if resolved else IncidentStatus.action_required,
                              symptoms=[question], diagnosis=cause,
                              resolution={"rootCause": cause, "successfulAction": action,
                                          "verifiedAt": "2026-10-08T00:00:00+00:00"} if resolved else None)
        return storage.create_incident(question, state)

    def test_only_verified_live_cases_become_oracles_and_distractors(self) -> None:
        first = self._incident("DB 연결이 끊어졌어요", "연결 풀 고갈", "누수 수정")
        second = self._incident("DB 쓰기가 지연돼요", "락 경합", "긴 트랜잭션 종료")
        self._incident("DB 응답이 느려요", "임시 추정", "재시작", resolved=False)
        self._incident("DB 인증 오류", "예시 원인", "예시 조치", origin="example")

        cases = dataset.verified_cases()
        self.assertEqual([case["id"] for case in cases], [first, second])
        samples = dataset.examples(cases)
        self.assertEqual(len(samples), 4)
        positive = next(item for item in samples if item["metadata"]["source_incident_id"] == first
                        and item["metadata"]["variant"] == "oracle")
        negative = next(item for item in samples if item["metadata"]["source_incident_id"] == first
                        and item["metadata"]["variant"] == "no_oracle_abstain")
        self.assertEqual(positive["metadata"]["distractor_document_ids"], [second])
        self.assertIn(first, positive["messages"][2]["content"])
        self.assertIn("누수 수정", positive["messages"][2]["content"])
        self.assertEqual([doc["id"] for doc in json.loads(negative["messages"][1]["content"])["documents"]], [second])
        self.assertIn("찾지 못했습니다", negative["messages"][2]["content"])
        self.assertEqual(positive["metadata"]["split"], negative["metadata"]["split"])
        self.assertEqual(samples, dataset.examples(cases))
        self.assertFalse(raft_dataset_status()["ready_for_fine_tuning"])

        async def downloaded() -> list[dict]:
            response = download_raft_dataset()
            return [json.loads(chunk) async for chunk in response.body_iterator]

        self.assertEqual(asyncio.run(downloaded()), samples)

    def test_duplicate_question_or_answer_does_not_become_false_distractor(self) -> None:
        first = self._incident("DB 연결이 끊어졌어요", "연결 풀 고갈", "누수 수정")
        self._incident("DB 연결이 끊어졌어요", "다른 원인", "다른 조치")
        self._incident("저장 API 오류", "연결 풀 고갈", "같은 원인 조치")
        samples = dataset.examples()
        source = next(item for item in samples if item["metadata"]["source_incident_id"] == first)
        self.assertEqual(source["metadata"]["distractor_document_ids"], [])
        self.assertEqual(source["metadata"]["variant"], "oracle")

    def test_distractors_do_not_cross_train_validation_boundary(self) -> None:
        train = next(f"질문 {i}" for i in range(100) if dataset._split(f"질문 {i}") == "train")
        validation = next(f"질문 {i}" for i in range(100) if dataset._split(f"질문 {i}") == "validation")
        self._incident(train, "원인 A", "조치 A")
        self._incident(validation, "원인 B", "조치 B")
        rows = dataset.examples()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not row["metadata"]["distractor_document_ids"] for row in rows))


if __name__ == "__main__":
    unittest.main()
