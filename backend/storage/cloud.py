"""Supabase-backed incident repository for stateless hosting."""

from __future__ import annotations

import json
import secrets
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from backend.models import IncidentState
from backend.storage.supabase import _secret, DEFAULT_URL
import os


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request(table: str, *, method: str = "GET", params: dict[str, str] | None = None,
             body: dict[str, Any] | None = None, upsert: bool = False) -> list[dict[str, Any]]:
    key = _secret()
    if not key:
        raise RuntimeError("SUPABASE_SECRET_KEY is required for cloud storage")
    query = urllib.parse.urlencode(params or {})
    url = f"{os.getenv('SUPABASE_URL', DEFAULT_URL).rstrip('/')}/rest/v1/{table}"
    if query:
        url += "?" + query
    headers = {"apikey": key, "Content-Type": "application/json", "Accept": "application/json",
               "Prefer": "return=representation" + (",resolution=merge-duplicates" if upsert else "")}
    if key.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + key
    request = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
                                     headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=12) as response:
        data = response.read()
    return json.loads(data) if data else []


def _mapped(row: dict[str, Any]) -> dict[str, Any]:
    return {"id": row["id"], "message": row["question"], "state": row["state"],
            "created_at": row["created_at"], "updated_at": row["updated_at"]}


def create_incident(message: str, state: IncidentState) -> str:
    incident_id = "INC-" + secrets.token_hex(6).upper()
    state.id = incident_id
    now = _now()
    _request("raft_incidents", method="POST", body={"id": incident_id, "question": message,
             "situation": "; ".join(state.symptoms), "diagnosis": state.diagnosis,
             "actions": state.immediateActions, "domain": state.classification.domain if state.classification else "UNKNOWN",
             "status": state.status.value, "state": state.model_dump(mode="json"),
             "created_at": now, "updated_at": now})
    return incident_id


def save_state(state: IncidentState) -> None:
    verified = state.status.value == "resolved" and bool(state.resolution)
    _request("raft_incidents", method="PATCH", params={"id": f"eq.{state.id}"}, body={
        "situation": "; ".join(state.symptoms),
        "diagnosis": state.resolution["rootCause"] if verified else state.diagnosis,
        "actions": [state.resolution["successfulAction"]] if verified else state.immediateActions,
        "domain": state.classification.domain if state.classification else "UNKNOWN",
        "status": state.status.value, "state": state.model_dump(mode="json"), "updated_at": _now()})


def get_incident(incident_id: str) -> dict[str, Any] | None:
    rows = _request("raft_incidents", params={"id": f"eq.{incident_id}", "select": "*", "limit": "1"})
    return _mapped(rows[0]) if rows else None


def list_incidents(status: str | None = None) -> list[dict[str, Any]]:
    params = {"select": "*", "order": "created_at.desc", "limit": "100"}
    if status and status != "active":
        params["status"] = f"eq.{status}"
    rows = [_mapped(row) for row in _request("raft_incidents", params=params)]
    return [row for row in rows if row["state"]["status"] != "resolved"] if status == "active" else rows


def list_all_incidents() -> list[dict[str, Any]]:
    results = []
    offset = 0
    while True:
        rows = _request("raft_incidents", params={"select": "*", "order": "created_at.asc", "limit": "1000", "offset": str(offset)})
        results.extend(_mapped(row) for row in rows)
        if len(rows) < 1000:
            break
        offset += 1000
    return results


def append_event(incident_id: str, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    rows = _request("raft_events", method="POST", body={"incident_id": incident_id,
                    "type": event_type, "data": data, "created_at": _now()})
    return rows[0]


def get_events(incident_id: str, after_id: int = 0) -> list[dict[str, Any]]:
    return _request("raft_events", params={"incident_id": f"eq.{incident_id}", "id": f"gt.{after_id}",
                                          "select": "*", "order": "id.asc", "limit": "1000"})


def record_action(action_id: str, incident_id: str, decision: str) -> None:
    # The caller persists the decision in IncidentState and the event stream.
    return None


def list_knowledge(status: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    params = {"select": "*", "order": "updated_at.desc", "limit": str(limit)}
    if status == "resolved":
        params["status"] = "eq.resolved"
    rows = _request("raft_incidents", params=params)
    result = []
    for row in rows:
        verified = row["status"] == "resolved" and bool(row["state"].get("resolution"))
        knowledge_status = "resolved" if verified else "unverified" if row["status"] == "resolved" else row["status"]
        if status and knowledge_status != status:
            continue
        result.append({"incident_id": row["id"], "question": row["question"], "situation": row["situation"],
                       "diagnosis": row["diagnosis"], "actions": row["actions"], "domain": row["domain"],
                       "status": knowledge_status, "updated_at": row["updated_at"]})
    return result


def list_faq() -> list[dict[str, Any]]:
    return _request("raft_faq", params={"select": "*", "order": "updated_at.desc", "limit": "1000"})


def save_faq(signature: str, question: str, answer: str) -> dict[str, Any]:
    rows = _request("raft_faq", method="POST", params={"on_conflict": "signature"},
                    body={"signature": signature, "question": question, "answer": answer, "updated_at": _now()}, upsert=True)
    return rows[0]
