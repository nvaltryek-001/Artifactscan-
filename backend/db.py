"""SQLite persistence: schema, lightweight migrations and audit events."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return str(uuid.uuid4())


@contextmanager
def connect():
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT DEFAULT '',
    provenance TEXT DEFAULT '',
    rights TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    media_type TEXT NOT NULL,
    checksum TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    message TEXT DEFAULT '',
    output_dir TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS predictions (
    id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    model_version TEXT NOT NULL,
    predicted_label TEXT NOT NULL,
    scores_json TEXT NOT NULL,
    status TEXT NOT NULL,
    reviewer_label TEXT DEFAULT '',
    reviewed_at TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    details_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assets_artifact ON assets(artifact_id);
CREATE INDEX IF NOT EXISTS idx_jobs_artifact ON jobs(artifact_id);
CREATE INDEX IF NOT EXISTS idx_predictions_artifact ON predictions(artifact_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at);
"""

# Columns added after the first MVP release. Existing databases are upgraded
# in place with ALTER TABLE, so no user data is lost.
MIGRATIONS = {
    "artifacts": {
        "creator": "TEXT DEFAULT ''",
        "period": "TEXT DEFAULT ''",
        "material": "TEXT DEFAULT ''",
        "dimensions": "TEXT DEFAULT ''",
        "origin": "TEXT DEFAULT ''",
        "condition": "TEXT DEFAULT ''",
        "license_url": "TEXT DEFAULT ''",
        "review_status": "TEXT DEFAULT 'draft'",
        "updated_at": "TEXT DEFAULT ''",
    },
    "assets": {
        "original_filename": "TEXT DEFAULT ''",
        "size_bytes": "INTEGER DEFAULT 0",
        "width": "INTEGER DEFAULT 0",
        "height": "INTEGER DEFAULT 0",
    },
    "jobs": {
        "engine": "TEXT DEFAULT ''",
        "stats_json": "TEXT DEFAULT '{}'",
        "started_at": "TEXT DEFAULT ''",
        "finished_at": "TEXT DEFAULT ''",
        "output_checksum": "TEXT DEFAULT ''",
    },
}


def init_db() -> None:
    with connect() as con:
        con.executescript(SCHEMA)
        for table, columns in MIGRATIONS.items():
            existing = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
            for name, decl in columns.items():
                if name not in existing:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        # Jobs left running by a previous process can never finish.
        con.execute(
            "UPDATE jobs SET status='failed', stage='interrupted', "
            "message='Server restarted while this job was running.', updated_at=? "
            "WHERE status IN ('queued','running')",
            (now(),),
        )


def audit(con: sqlite3.Connection, entity_type: str, entity_id: str,
          action: str, **details) -> None:
    con.execute(
        "INSERT INTO audit_events (entity_type, entity_id, action, details_json, created_at) "
        "VALUES (?,?,?,?,?)",
        (entity_type, entity_id, action, json.dumps(details, default=str), now()),
    )
