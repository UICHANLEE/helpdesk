from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from backend.api.incidents import update_status, update_workflow
from backend.models import IncidentState, IncidentStatus, StatusUpdateRequest, WorkflowStage, WorkflowUpdateRequest
from backend.storage import sqlite as storage


class WorkflowTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = storage.DB_PATH
        storage.DB_PATH = Path(self.temp.name) / "workflow.sqlite3"
        storage.init_db()

    async def asyncTearDown(self) -> None:
        storage.DB_PATH = self.old_path
        self.temp.cleanup()

    async def test_card_moves_are_saved_and_done_requires_resolution(self) -> None:
        incident_id = storage.create_incident("API 오류", IncidentState(id="", workflowStage=WorkflowStage.todo))
        moved = await update_workflow(incident_id, WorkflowUpdateRequest(stage=WorkflowStage.in_progress))
        self.assertEqual(moved["workflowStage"], "in_progress")
        with self.assertRaises(HTTPException):
            await update_workflow(incident_id, WorkflowUpdateRequest(stage=WorkflowStage.review))
        with self.assertRaises(HTTPException):
            await update_workflow(incident_id, WorkflowUpdateRequest(stage=WorkflowStage.done))
        state = IncidentState.model_validate(storage.get_incident(incident_id)["state"])
        state.status = IncidentStatus.investigating
        storage.save_state(state)
        with self.assertRaises(HTTPException):
            await update_workflow(incident_id, WorkflowUpdateRequest(stage=WorkflowStage.todo))
        state.status = IncidentStatus.action_required
        storage.save_state(state)
        moved = await update_workflow(incident_id, WorkflowUpdateRequest(stage=WorkflowStage.review))
        self.assertEqual(moved["workflowStage"], "review")
        self.assertEqual(storage.get_events(incident_id)[-1]["type"], "workflow_changed")
        resolved = await update_status(incident_id, StatusUpdateRequest(status=IncidentStatus.resolved,
                               root_cause="API 라우트 오류", successful_action="경로 수정"))
        self.assertEqual(resolved["workflowStage"], "done")
        with self.assertRaises(HTTPException):
            await update_workflow(incident_id, WorkflowUpdateRequest(stage=WorkflowStage.in_progress))


if __name__ == "__main__":
    unittest.main()
