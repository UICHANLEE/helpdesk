"""Consistent, local SQLite snapshots kept outside Git."""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.storage import sqlite as storage

BACKUP_DIR = Path(os.getenv("RAFT_BACKUP_DIR", str(Path(__file__).resolve().parents[1] / "backups")))
KST = ZoneInfo("Asia/Seoul")
_lock = threading.Lock()


def backup_now() -> dict:
    if not storage.DB_PATH.exists():
        raise FileNotFoundError("Local incident database does not exist")
    with _lock:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        BACKUP_DIR.chmod(0o700)
        day = datetime.now(KST).date().isoformat()
        target = BACKUP_DIR / f"raft-{day}.sqlite3"
        temporary = BACKUP_DIR / f".raft-{day}.tmp"
        temporary.unlink(missing_ok=True)
        try:
            with closing(sqlite3.connect(storage.DB_PATH)) as source, closing(sqlite3.connect(temporary)) as copy:
                source.backup(copy)
                if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("SQLite backup integrity check failed")
            temporary.chmod(0o600)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return status()


def status() -> dict:
    files = sorted(BACKUP_DIR.glob("raft-*.sqlite3"), key=lambda path: path.stat().st_mtime, reverse=True)
    latest = files[0] if files else None
    return {"database_path": str(storage.DB_PATH), "backup_dir": str(BACKUP_DIR),
            "backup_count": len(files), "latest_backup": latest.name if latest else None,
            "latest_backup_at": datetime.fromtimestamp(latest.stat().st_mtime, timezone.utc).isoformat() if latest else None}
