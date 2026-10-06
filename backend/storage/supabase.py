"""Durable SQLite outbox mirrored to Supabase Data API from the backend only."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from backend.storage import sqlite as storage

DEFAULT_URL = "https://opwzujhfsxqaivtbjewg.supabase.co"


def _secret() -> str | None:
    value = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if value:
        return value.strip()
    path = Path(os.getenv("SUPABASE_SECRET_KEY_FILE", str(Path(__file__).resolve().parents[2] / "secrets" / "supabase_secret_key.txt")))
    try:
        return path.read_text().strip() or None
    except OSError:
        return None


def configured() -> bool:
    return bool(_secret())


def status() -> dict:
    return {"configured": configured(), "project_url": os.getenv("SUPABASE_URL", DEFAULT_URL),
            "pending": len(storage.pending_sync(10000))}


def _upsert(table: str, payload: dict) -> None:
    key = _secret()
    if not key:
        raise RuntimeError("Supabase secret key is not configured")
    url = os.getenv("SUPABASE_URL", DEFAULT_URL).rstrip("/") + "/rest/v1/" + table + "?on_conflict=id"
    headers = {"apikey": key, "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates,return=minimal"}
    if key.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + key
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=8):
        pass


def flush(limit: int = 50) -> dict:
    if not configured():
        return {"synced": 0, "pending": len(storage.pending_sync(10000)), "status": "unconfigured"}
    count = 0
    error = None
    for item in storage.pending_sync(limit):
        try:
            payload = json.loads(item["payload"])
            table = {"incident": "raft_incidents", "event": "raft_events", "faq": "raft_faq"}[item["kind"]]
            _upsert(table, payload)
            storage.synced(item["kind"], item["record_id"], item["updated_at"])
            count += 1
        except (OSError, ValueError, RuntimeError) as exc:
            error = f"{type(exc).__name__}: {getattr(exc, 'code', 'connection error')}"
            break
    return {"synced": count, "pending": len(storage.pending_sync(10000)),
            "status": "error" if error else "connected", "error": error}
