from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class CommandLifecycleStore:
    """Persistent command state machine ledger for NT8 API orchestration."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path.resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS commands (
                    cmd_id TEXT PRIMARY KEY,
                    request_id TEXT,
                    trace_id TEXT,
                    instance_id TEXT,
                    command TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    final_state TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cmd_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    message TEXT,
                    error_code TEXT,
                    retryable INTEGER NOT NULL DEFAULT 0,
                    payload_json TEXT,
                    FOREIGN KEY (cmd_id) REFERENCES commands(cmd_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dead_letters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cmd_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    ts_ms INTEGER NOT NULL,
                    payload_json TEXT,
                    FOREIGN KEY (cmd_id) REFERENCES commands(cmd_id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_transitions_cmd ON transitions(cmd_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_transitions_ts ON transitions(ts_ms)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_commands_created ON commands(created_at_ms)")
            conn.commit()

    def create_command(
        self,
        *,
        cmd_id: str,
        request_id: str | None,
        trace_id: str | None,
        instance_id: str | None,
        command: str,
    ) -> None:
        now_ms = int(time.time() * 1000)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO commands
                    (cmd_id, request_id, trace_id, instance_id, command, created_at_ms, final_state, attempts)
                    VALUES (?, ?, ?, ?, ?, ?, NULL, 0)
                    """,
                    (cmd_id, request_id, trace_id, instance_id, command, now_ms),
                )
                conn.commit()

    def transition(
        self,
        *,
        cmd_id: str,
        state: str,
        message: str = "",
        error_code: str | None = None,
        retryable: bool = False,
        payload: dict[str, Any] | None = None,
    ) -> None:
        now_ms = int(time.time() * 1000)
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        final_state = state if state in ("done", "failed") else None

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO transitions
                    (cmd_id, state, ts_ms, message, error_code, retryable, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (cmd_id, state, now_ms, message, error_code, int(retryable), payload_json),
                )
                conn.execute(
                    "UPDATE commands SET attempts = attempts + 1, final_state = COALESCE(?, final_state) WHERE cmd_id = ?",
                    (final_state, cmd_id),
                )
                conn.commit()

    def add_dead_letter(self, *, cmd_id: str, reason: str, payload: dict[str, Any] | None = None) -> None:
        now_ms = int(time.time() * 1000)
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO dead_letters (cmd_id, reason, ts_ms, payload_json) VALUES (?, ?, ?, ?)",
                    (cmd_id, reason, now_ms, payload_json),
                )
                conn.commit()

    def metrics(self, since_seconds: int = 3600) -> dict[str, Any]:
        cutoff_ms = int((time.time() - max(1, since_seconds)) * 1000)
        with self._lock:
            with self._connect() as conn:
                total = conn.execute(
                    "SELECT COUNT(*) AS c FROM commands WHERE created_at_ms >= ?",
                    (cutoff_ms,),
                ).fetchone()["c"]
                done = conn.execute(
                    "SELECT COUNT(*) AS c FROM commands WHERE created_at_ms >= ? AND final_state = 'done'",
                    (cutoff_ms,),
                ).fetchone()["c"]
                failed = conn.execute(
                    "SELECT COUNT(*) AS c FROM commands WHERE created_at_ms >= ? AND final_state = 'failed'",
                    (cutoff_ms,),
                ).fetchone()["c"]
                dead = conn.execute(
                    "SELECT COUNT(*) AS c FROM dead_letters WHERE ts_ms >= ?",
                    (cutoff_ms,),
                ).fetchone()["c"]
                top_errors = conn.execute(
                    """
                    SELECT error_code, COUNT(*) AS c
                    FROM transitions
                    WHERE ts_ms >= ? AND error_code IS NOT NULL AND error_code != ''
                    GROUP BY error_code
                    ORDER BY c DESC
                    LIMIT 10
                    """,
                    (cutoff_ms,),
                ).fetchall()
        success_rate = (float(done) / float(total)) if total else 1.0
        return {
            "since_seconds": since_seconds,
            "total_commands": int(total),
            "done": int(done),
            "failed": int(failed),
            "dead_letters": int(dead),
            "success_rate": round(success_rate, 6),
            "top_error_codes": [{"error_code": r["error_code"], "count": int(r["c"])} for r in top_errors],
        }

    def recent_errors(self, limit: int = 50) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit), 500))
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT t.ts_ms, t.cmd_id, c.command, c.request_id, c.trace_id, c.instance_id,
                           t.state, t.message, t.error_code, t.retryable, t.payload_json
                    FROM transitions t
                    JOIN commands c ON c.cmd_id = t.cmd_id
                    WHERE t.error_code IS NOT NULL AND t.error_code != ''
                    ORDER BY t.id DESC
                    LIMIT ?
                    """,
                    (lim,),
                ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except Exception:
                payload = {}
            out.append(
                {
                    "ts_ms": int(row["ts_ms"]),
                    "cmd_id": row["cmd_id"],
                    "command": row["command"],
                    "request_id": row["request_id"],
                    "trace_id": row["trace_id"],
                    "instance_id": row["instance_id"],
                    "state": row["state"],
                    "message": row["message"],
                    "error_code": row["error_code"],
                    "retryable": bool(row["retryable"]),
                    "payload": payload,
                }
            )
        return out
