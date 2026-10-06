from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.agent.orchestrator import investigate
from backend.api.incidents import find_trace, update_status
from backend.api.tools import execute_tool
from backend.models import Classification, IncidentState, IncidentStatus, StatusUpdateRequest, ToolExecuteRequest
from backend.observability.trace import graph
from backend.storage import sqlite as storage


class TraceWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = storage.DB_PATH
        storage.DB_PATH = Path(self.temp.name) / "trace.sqlite3"
        storage.init_db()

    def tearDown(self) -> None:
        storage.DB_PATH = self.old_path
        self.temp.cleanup()

    def test_claim_links_to_real_events_without_claiming_verification(self) -> None:
        judgment = {"primary": "DATABASE", "secondary": "API", "severity": "P2", "depth": "MEDIUM"}
        parsed = {"text": "DB 저장 실패", "signals": ["저장 API 오류"]}
        state = IncidentState(id="", classification=Classification(domain="DATABASE"),
                              symptoms=parsed["signals"], providerStatus={"qwen": "pending"})
        incident_id = storage.create_incident(parsed["text"], state)
        storage.append_event(incident_id, "user", {"message": parsed["text"]})

        async def tool_result(name: str, _: dict) -> dict:
            return {"name": name, "status": "ok" if name == "db_health" else "error",
                    "summary": "DB 연결 정상" if name == "db_health" else "HTTP 500"}

        with patch("backend.agent.orchestrator.retrieve", new=AsyncMock(return_value=[
                {"id": "INC-381", "title": "과거 장애", "score": .92}])), \
             patch("backend.agent.orchestrator.tools_for", return_value=["db_health", "api_health"]), \
             patch("backend.agent.orchestrator.get_tool_config", return_value={"db_health": "local", "api_health": "local"}), \
             patch("backend.agent.orchestrator.execute", new=AsyncMock(side_effect=tool_result)), \
             patch("backend.agent.orchestrator.qwen_diagnose", new=AsyncMock(return_value={
                 "diagnosis": "DB 저장 API 실패", "immediate_actions": ["API 로그 확인"],
                 "recommended_action": "API 로그 확인", "hypotheses": []})):
            asyncio.run(investigate(incident_id, parsed, judgment))

        record = storage.get_incident(incident_id)
        events = storage.get_events(incident_id)
        trace = graph(record, events)
        self.assertEqual(trace["trace_id"], f"TR-{incident_id}")
        self.assertEqual(find_trace(trace["trace_id"])["trace_id"], trace["trace_id"])
        self.assertEqual(trace["claims"][0]["verification"], "unverified")
        self.assertEqual({link["relation"] for link in trace["edges"] if link["from"].endswith("-C1")},
                         {"reported", "historical_match", "observed", "failed_check"})
        self.assertEqual({item["status"] for item in trace["spans"] if item["kind"] == "tool"}, {"ok", "error"})
        self.assertTrue(all(item["duration_ms"] >= 0 for item in trace["spans"] if item["kind"] == "tool"))
        self.assertTrue(any(item["kind"] == "llm" for item in trace["spans"]))
        self.assertEqual(trace["signals"]["tool_failures"], 1)
        self.assertEqual(trace["signals"]["confirmed_checks"], 1)

        with patch("backend.api.tools.get_tool_config", return_value={"db_health": "local"}), \
             patch("backend.api.tools.execute", new=AsyncMock(return_value={
                 "name": "db_health", "status": "ok", "summary": "추가 점검 정상"})):
            asyncio.run(execute_tool(ToolExecuteRequest(incident_id=incident_id, tool="db_health")))
        followed_up = graph(storage.get_incident(incident_id), storage.get_events(incident_id))
        self.assertIn("follow_up_check", {edge["relation"] for edge in followed_up["edges"]})

        asyncio.run(update_status(incident_id, StatusUpdateRequest(
            status=IncidentStatus.resolved, root_cause="저장 API 결함", successful_action="API 수정")))
        verified = graph(storage.get_incident(incident_id), storage.get_events(incident_id))
        self.assertEqual(verified["claims"][-1]["verification"], "operator_verified")
        self.assertIn("operator_verification", {edge["relation"] for edge in verified["edges"]})


if __name__ == "__main__":
    unittest.main()
