from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from backend.models import IncidentState

DB_PATH = Path(os.getenv("RAFT_DB_PATH", str(Path(__file__).resolve().parents[1] / "data" / "raft.sqlite3")))
_lock = threading.Lock()


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    DB_PATH.parent.chmod(0o700)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    DB_PATH.chmod(0o600)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db() -> None:
    with _connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS incidents (
            id TEXT PRIMARY KEY, message TEXT NOT NULL, state TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id TEXT NOT NULL,
            type TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS events_incident_idx ON events(incident_id, id);
        CREATE TABLE IF NOT EXISTS actions (
            id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, decision TEXT,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS knowledge (
            incident_id TEXT PRIMARY KEY, question TEXT NOT NULL, situation TEXT NOT NULL,
            diagnosis TEXT NOT NULL, actions TEXT NOT NULL, domain TEXT NOT NULL,
            status TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS knowledge_status_idx ON knowledge(status, updated_at);
        CREATE TABLE IF NOT EXISTS faq (
            id INTEGER PRIMARY KEY AUTOINCREMENT, signature TEXT NOT NULL UNIQUE,
            question TEXT NOT NULL, answer TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sheet_sync (
            id INTEGER PRIMARY KEY CHECK(id = 1), completed_at TEXT NOT NULL,
            updated_rows INTEGER NOT NULL, inserted_rows INTEGER NOT NULL,
            unchanged_rows INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS knowledge_vectors (
            document_id TEXT PRIMARY KEY, model TEXT NOT NULL, content_hash TEXT NOT NULL,
            dimensions INTEGER NOT NULL, embedding BLOB NOT NULL, updated_at TEXT NOT NULL
        );
        """)
        for row in db.execute("SELECT id, message, state, created_at, updated_at FROM incidents").fetchall():
            _index_incident(db, row["id"], row["message"], IncidentState.model_validate_json(row["state"]), row["updated_at"])


def _index_incident(db: sqlite3.Connection, incident_id: str, message: str, state: IncidentState, now: str) -> None:
    domain = state.classification.domain if state.classification else "UNKNOWN"
    verified = state.status.value == "resolved" and bool(state.resolution)
    knowledge_status = ("example" if state.examplePhase == "reviewed" else "example_pending") if state.origin == "example" else "resolved" if verified else "unverified" if state.status.value == "resolved" else state.status.value
    diagnosis = state.resolution["rootCause"] if verified else state.diagnosis
    actions = [state.resolution["successfulAction"]] if verified else state.immediateActions
    db.execute("""INSERT INTO knowledge VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(incident_id) DO UPDATE SET question=excluded.question, situation=excluded.situation,
        diagnosis=excluded.diagnosis, actions=excluded.actions, domain=excluded.domain,
        status=excluded.status, updated_at=excluded.updated_at""",
        (incident_id, message, "; ".join(state.symptoms), diagnosis,
         json.dumps(actions, ensure_ascii=False), domain, knowledge_status, now))


def create_incident(message: str, state: IncidentState) -> str:
    now = datetime.now(timezone.utc).isoformat()
    with _lock, _connection() as db:
        number = db.execute("SELECT COALESCE(MAX(CAST(SUBSTR(id, 5) AS INTEGER)), 1000) + 1 FROM incidents").fetchone()[0]
        incident_id = f"INC-{number}"
        state.id = incident_id
        db.execute("INSERT INTO incidents VALUES (?, ?, ?, ?, ?)", (incident_id, message, state.model_dump_json(), now, now))
        _index_incident(db, incident_id, message, state, now)
    return incident_id


def save_state(state: IncidentState) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _lock, _connection() as db:
        row = db.execute("SELECT message FROM incidents WHERE id=?", (state.id,)).fetchone()
        if row:
            db.execute("UPDATE incidents SET state=?, updated_at=? WHERE id=?", (state.model_dump_json(), now, state.id))
            _index_incident(db, state.id, row["message"], state, now)


def get_incident(incident_id: str) -> dict[str, Any] | None:
    with _connection() as db:
        row = db.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
    if not row:
        return None
    return {"id": row["id"], "message": row["message"], "state": json.loads(row["state"]), "created_at": row["created_at"], "updated_at": row["updated_at"]}


def list_incidents(status: str | None = None) -> list[dict[str, Any]]:
    with _connection() as db:
        rows = db.execute("SELECT * FROM incidents ORDER BY created_at DESC LIMIT 1000").fetchall()
    incidents = [{"id": row["id"], "message": row["message"], "state": json.loads(row["state"]), "created_at": row["created_at"], "updated_at": row["updated_at"]} for row in rows]
    incidents.sort(key=lambda item: item["state"].get("origin") == "example")
    if status == "examples":
        return [item for item in incidents if item["state"].get("origin") == "example"]
    incidents = [item for item in incidents if item["state"].get("origin") != "example"]
    if status == "active":
        return [item for item in incidents if item["state"]["status"] != "resolved"]
    return [item for item in incidents if item["state"]["status"] == status] if status else incidents


def append_event(incident_id: str, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with _connection() as db:
        cursor = db.execute("INSERT INTO events(incident_id, type, data, created_at) VALUES (?, ?, ?, ?)", (incident_id, event_type, json.dumps(data, ensure_ascii=False), now))
        event_id = cursor.lastrowid
    return {"id": event_id, "incident_id": incident_id, "type": event_type, "data": data, "created_at": now}


def get_events(incident_id: str, after_id: int = 0) -> list[dict[str, Any]]:
    with _connection() as db:
        rows = db.execute("SELECT * FROM events WHERE incident_id=? AND id>? ORDER BY id", (incident_id, after_id)).fetchall()
    return [{"id": row["id"], "incident_id": row["incident_id"], "type": row["type"], "data": json.loads(row["data"]), "created_at": row["created_at"]} for row in rows]


def record_action(action_id: str, incident_id: str, decision: str) -> None:
    with _connection() as db:
        db.execute("INSERT INTO actions(id, incident_id, decision, updated_at) VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET decision=excluded.decision, updated_at=excluded.updated_at", (action_id, incident_id, decision, datetime.now(timezone.utc).isoformat()))


def list_knowledge(status: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    with _connection() as db:
        rows = db.execute("SELECT * FROM knowledge WHERE (? IS NULL OR status=?) ORDER BY updated_at DESC LIMIT ?", (status, status, limit)).fetchall()
    return [{**dict(row), "actions": json.loads(row["actions"])} for row in rows]


def list_all_incidents() -> list[dict[str, Any]]:
    with _connection() as db:
        rows = db.execute("SELECT * FROM incidents ORDER BY created_at").fetchall()
    return [{"id": row["id"], "message": row["message"], "state": json.loads(row["state"]), "created_at": row["created_at"], "updated_at": row["updated_at"]} for row in rows]


def list_faq() -> list[dict[str, Any]]:
    with _connection() as db:
        rows = db.execute("SELECT * FROM faq ORDER BY updated_at DESC").fetchall()
    return [dict(row) for row in rows]


def save_faq(signature: str, question: str, answer: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with _connection() as db:
        db.execute("""INSERT INTO faq(signature, question, answer, updated_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(signature) DO UPDATE SET question=excluded.question, answer=excluded.answer,
            updated_at=excluded.updated_at""", (signature, question, answer, now))
        row = db.execute("SELECT * FROM faq WHERE signature=?", (signature,)).fetchone()
    return dict(row)


def list_vectors(model: str) -> list[dict[str, Any]]:
    with _connection() as db:
        rows = db.execute("SELECT * FROM knowledge_vectors WHERE model=?", (model,)).fetchall()
    return [dict(row) for row in rows]


def save_vectors(rows: list[tuple[str, str, str, int, bytes]]) -> None:
    if not rows:
        return
    now = datetime.now(timezone.utc).isoformat()
    with _lock, _connection() as db:
        db.executemany("""INSERT INTO knowledge_vectors VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET model=excluded.model,
            content_hash=excluded.content_hash, dimensions=excluded.dimensions,
            embedding=excluded.embedding, updated_at=excluded.updated_at""",
            [(*row, now) for row in rows])


def delete_stale_vectors(document_ids: set[str], model: str) -> None:
    with _lock, _connection() as db:
        existing = [row[0] for row in db.execute("SELECT document_id FROM knowledge_vectors WHERE model=?", (model,))]
        db.executemany("DELETE FROM knowledge_vectors WHERE document_id=?", [(key,) for key in existing if key not in document_ids])


def get_sheet_sync() -> dict[str, Any] | None:
    with _connection() as db:
        try:
            row = db.execute("SELECT * FROM sheet_sync WHERE id=1").fetchone()
        except sqlite3.OperationalError:
            return None  # Status remains readable until the next application startup migrates the DB.
    return dict(row) if row else None


def record_sheet_sync(updated_rows: int, inserted_rows: int, unchanged_rows: int) -> dict[str, Any]:
    completed_at = datetime.now(timezone.utc).isoformat()
    with _connection() as db:
        db.execute("""INSERT INTO sheet_sync VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET completed_at=excluded.completed_at,
            updated_rows=excluded.updated_rows, inserted_rows=excluded.inserted_rows,
            unchanged_rows=excluded.unchanged_rows""",
            (completed_at, updated_rows, inserted_rows, unchanged_rows))
    return {"completed_at": completed_at, "updated_rows": updated_rows,
            "inserted_rows": inserted_rows, "unchanged_rows": unchanged_rows}
