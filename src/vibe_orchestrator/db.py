from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def encode_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def decode_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    return json.loads(value)


class Store:
    def __init__(self, db_path: Path, event_log_path: Path):
        self.db_path = Path(db_path)
        self.event_log_path = Path(event_log_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def create_job(
        self,
        *,
        work_package: str,
        provider_family: str = "fake",
        model: str = "fake",
        priority: int = 50,
        affected: list[str] | None = None,
    ) -> dict[str, Any]:
        job_id = new_id("job")
        now = utc_now()
        affected_json = encode_json(affected or [])
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, status, provider_family, model, work_package,
                    priority, affected_json, created_at, updated_at
                )
                VALUES (?, 'pending', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    provider_family,
                    model,
                    work_package,
                    priority,
                    affected_json,
                    now,
                    now,
                ),
            )
        self.append_event(
            job_id=job_id,
            source_type="user",
            source_id=None,
            event_type="job.created",
            payload={
                "provider_family": provider_family,
                "model": model,
                "priority": priority,
                "affected": affected or [],
            },
        )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return normalize_job(row)

    def list_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM jobs
                ORDER BY
                    CASE status
                        WHEN 'running' THEN 0
                        WHEN 'pending' THEN 1
                        WHEN 'paused' THEN 2
                        WHEN 'done' THEN 3
                        ELSE 4
                    END,
                    priority DESC,
                    created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [normalize_job(row) for row in rows]

    def update_job_status(self, job_id: str, status: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                (status, now, job_id),
            )
        self.append_event(
            job_id=job_id,
            source_type="scheduler",
            source_id=None,
            event_type=f"job.{status}",
            payload=payload or {},
        )
        return self.get_job(job_id)

    def create_agent(self, *, job_id: str, provider_family: str, model: str) -> dict[str, Any]:
        agent_id = new_id("agent")
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO agents (
                    agent_id, job_id, provider_family, model, status,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'starting', ?, ?)
                """,
                (agent_id, job_id, provider_family, model, now, now),
            )
        self.append_event(
            job_id=job_id,
            source_type="adapter",
            source_id=agent_id,
            event_type="agent.spawned",
            payload={"provider_family": provider_family, "model": model},
        )
        return self.get_agent(agent_id)

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
        if row is None:
            raise KeyError(agent_id)
        return dict(row)

    def list_agents(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM agents
                ORDER BY
                    CASE status
                        WHEN 'running' THEN 0
                        WHEN 'starting' THEN 1
                        WHEN 'paused' THEN 2
                        WHEN 'done' THEN 3
                        ELSE 4
                    END,
                    created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_agent_status(self, agent_id: str, status: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        now = utc_now()
        agent = self.get_agent(agent_id)
        with self.connect() as conn:
            conn.execute(
                "UPDATE agents SET status = ?, updated_at = ? WHERE agent_id = ?",
                (status, now, agent_id),
            )
        self.append_event(
            job_id=agent["job_id"],
            source_type="adapter",
            source_id=agent_id,
            event_type=f"agent.{status}",
            payload=payload or {},
        )
        return self.get_agent(agent_id)

    def append_message(
        self,
        *,
        agent_id: str | None,
        job_id: str | None,
        direction: str,
        message_type: str,
        payload: dict[str, Any],
        ack_status: str = "delivered",
    ) -> dict[str, Any]:
        message_id = new_id("msg")
        now = utc_now()
        payload_json = encode_json(payload)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    message_id, agent_id, job_id, direction, type,
                    payload_json, ack_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    agent_id,
                    job_id,
                    direction,
                    message_type,
                    payload_json,
                    ack_status,
                    now,
                    now,
                ),
            )
        self.append_event(
            job_id=job_id,
            source_type="agent" if direction == "agent_to_user" else "user",
            source_id=agent_id,
            event_type="agent.message" if agent_id else "message.created",
            payload={"direction": direction, "type": message_type, "payload": payload},
        )
        return self.get_message(message_id)

    def get_message(self, message_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM messages WHERE message_id = ?", (message_id,)).fetchone()
        if row is None:
            raise KeyError(message_id)
        return normalize_message(row)

    def list_messages(self, agent_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE agent_id = ?
                ORDER BY created_at ASC, message_id ASC
                LIMIT ?
                """,
                (agent_id, limit),
            ).fetchall()
        return [normalize_message(row) for row in rows]

    def append_event(
        self,
        *,
        job_id: str | None,
        source_type: str,
        source_id: str | None,
        event_type: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        payload_json = encode_json(payload)
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (
                    job_id, source_type, source_id, event_type, correlation_id,
                    payload_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, source_type, source_id, event_type, correlation_id, payload_json, now),
            )
            event_id = int(cursor.lastrowid)
        event = {
            "event_id": event_id,
            "job_id": job_id,
            "source_type": source_type,
            "source_id": source_id,
            "event_type": event_type,
            "correlation_id": correlation_id,
            "payload": payload,
            "created_at": now,
        }
        self._append_jsonl(event)
        return event

    def list_events(self, after: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM events
                WHERE event_id > ?
                ORDER BY event_id ASC
                LIMIT ?
                """,
                (after, limit),
            ).fetchall()
        return [normalize_event(row) for row in rows]

    def _append_jsonl(self, event: dict[str, Any]) -> None:
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.event_log_path.open("a", encoding="utf-8") as handle:
            handle.write(encode_json(event) + "\n")


def normalize_job(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["affected"] = decode_json(item.pop("affected_json"), [])
    return item


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> bool | None:
        result = super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return result


def normalize_message(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["payload"] = decode_json(item.pop("payload_json"), {})
    return item


def normalize_event(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["payload"] = decode_json(item.pop("payload_json"), {})
    return item


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    provider_family TEXT NOT NULL,
    model TEXT NOT NULL,
    work_package TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 50,
    affected_json TEXT NOT NULL DEFAULT '[]',
    base_commit TEXT,
    lease_owner_orchestrator TEXT,
    lease_expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    provider_family TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    pid INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS locks (
    lock_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    agent_id TEXT REFERENCES agents(agent_id) ON DELETE SET NULL,
    resource_type TEXT NOT NULL,
    resource_key TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    ttl_seconds INTEGER,
    heartbeat_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    agent_id TEXT REFERENCES agents(agent_id) ON DELETE CASCADE,
    job_id TEXT REFERENCES jobs(job_id) ON DELETE CASCADE,
    direction TEXT NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    ack_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(job_id) ON DELETE SET NULL,
    source_type TEXT NOT NULL,
    source_id TEXT,
    event_type TEXT NOT NULL,
    correlation_id TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    agent_id TEXT REFERENCES agents(agent_id) ON DELETE SET NULL,
    path TEXT NOT NULL,
    branch TEXT,
    base_commit TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_priority ON jobs(status, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_agents_job_id ON agents(job_id);
CREATE INDEX IF NOT EXISTS idx_locks_status_resource ON locks(status, resource_type, resource_key);
CREATE INDEX IF NOT EXISTS idx_messages_agent_id ON messages(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_event_id ON events(event_id);
CREATE INDEX IF NOT EXISTS idx_events_job_id ON events(job_id);
"""
