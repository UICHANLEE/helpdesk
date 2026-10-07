from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from incident import jev_judgment, parse_incident, rule_judgment
from backend.agent.orchestrator import investigate
from backend.knowledge.fallback import from_verified_history
from backend.knowledge.reassess import reassess, reclassify_explicit_llm
from backend.models import Classification, IncidentState, IncidentStatus, RaftMatch
from backend.storage import sqlite as storage


class HistoryFallbackTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = storage.DB_PATH
        storage.DB_PATH = Path(self.temp.name) / "history.sqlite3"
        storage.init_db()

    async def asyncTearDown(self) -> None:
        storage.DB_PATH = self.old_path
        self.temp.cleanup()

    async def test_missing_qwen_uses_verified_case_as_unconfirmed_check(self) -> None:
        incident_id = storage.create_incident("점심 이후 답변이 느려요", IncidentState(
            id="", classification=Classification(domain="UNKNOWN"),
            providerStatus={"qwen": "pending"}, symptoms=["점심 이후 답변 지연"]))
        matches = [
            {"id": "INC-1013", "title": "특정 시간대의 요청 집중", "summary": "확인된 해결 사례",
             "score": 0.11, "verification": "verified", "retrieval": "lexical"},
            {"id": "INC-1009", "title": "미해결", "summary": "미검증",
             "score": 0.12, "verification": "unverified", "retrieval": "lexical"},
        ]
        parsed = {"text": "점심 이후 답변이 느려요", "signals": []}
        judgment = {"primary": "UNKNOWN", "secondary": None, "severity": "P3", "depth": "MEDIUM", "source": "jev"}
        with patch("backend.agent.orchestrator.retrieve", return_value=matches), \
             patch("backend.agent.orchestrator.tools_for", return_value=[]), \
             patch("backend.agent.orchestrator.qwen_diagnose", return_value=None):
            await investigate(incident_id, parsed, judgment)
        state = storage.get_incident(incident_id)["state"]
        self.assertIn("INC-1013", state["diagnosis"])
        self.assertIn("미확인", state["diagnosis"])
        self.assertEqual(state["providerStatus"]["answer_source"], "verified_history_check")
        self.assertIn("INC-1013", state["recommendedAction"])
        self.assertEqual(state["status"], "action_required")
        self.assertIn("현재 건 검증 전", state["reasoningTrace"][2]["text"])

    def test_unverified_and_weak_matches_do_not_become_diagnoses(self) -> None:
        self.assertIsNone(from_verified_history([
            {"id": "INC-1", "title": "추정", "score": 0.7, "verification": "unverified", "retrieval": "hybrid"},
            {"id": "INC-2", "title": "과거 해결", "score": 0.1, "verification": "verified", "retrieval": "hybrid"},
        ]))

    def test_reassessment_updates_only_generic_open_case_and_preserves_audit(self) -> None:
        state = IncidentState(id="", status=IncidentStatus.action_required,
                              classification=Classification(domain="UNKNOWN"),
                              diagnosis="장애 영역을 더 확인해야 합니다", providerStatus={"qwen": "skipped"},
                              raftMatches=[RaftMatch(id="INC-1012", title="서버 자원 병목 가능성",
                                                     score=0.315, verification="verified", retrieval="hybrid")])
        incident_id = storage.create_incident("모델이 느려요", state)
        storage.append_event(incident_id, "retrieval", {"matches": ["INC-1012"]})
        self.assertTrue(reassess(incident_id))
        self.assertFalse(reassess(incident_id))
        updated = storage.get_incident(incident_id)["state"]
        self.assertIn("INC-1012", updated["diagnosis"])
        self.assertEqual(updated["status"], "action_required")
        self.assertEqual(storage.get_events(incident_id)[-1]["type"], "historical_reassessment")

    def test_explicit_llm_questions_override_unknown_route_and_reclassify(self) -> None:
        questions = ["모델 응답이 평소보다 느려졌을 때 무엇부터 확인해야 하나요?",
                     "특정 시간대에만 모델 응답 속도가 느려지는 이유는 무엇인가요?",
                     "점심 이후에 답변 속도가 너무 늦어지는ㄴ데 무슨 문제 있는거 아니에요?",
                     "포맷 드리프트를 어떻게 대처할 수 있어요?"]
        for question in questions:
            parsed = parse_incident(question)
            fallback = rule_judgment(parsed)
            self.assertEqual(fallback["primary"], "LLM")
            with patch("incident.typesafe_key", return_value="test"), \
                 patch("incident.post_json", return_value={"answers": {
                     "primary": {"choice": "UNKNOWN", "confidence": 0.9},
                     "secondary": {"choice": "UNKNOWN"}, "depth": {"choice": "SIMPLE"}}}):
                routed = jev_judgment(parsed, fallback)
            self.assertEqual(routed["primary"], "LLM")
            self.assertEqual(routed["source"], "rules_override")
        incident_id = storage.create_incident(questions[-1], IncidentState(
            id="", classification=Classification(domain="UNKNOWN")))
        self.assertTrue(reclassify_explicit_llm(incident_id))
        self.assertFalse(reclassify_explicit_llm(incident_id))
        self.assertEqual(storage.get_incident(incident_id)["state"]["classification"]["domain"], "LLM")
        self.assertEqual(storage.get_events(incident_id)[-1]["type"], "classification_revised")


if __name__ == "__main__":
    unittest.main()
