from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class NT8IdempotencyStore:
    """Lightweight request-id ledger for NT8 command API retries.

    Stores full response payloads by request_id so duplicate retries can replay
    the original result without re-executing command side effects.
    """

    def __init__(self, db_path: Path, ttl_seconds: int = 24 * 3600) -> None:
        self.db_path = db_path.resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
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
                CREATE TABLE IF NOT EXISTS idempotent_requests (
                    request_id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    args_json TEXT NOT NULL,
                    backend TEXT NOT NULL,
                    prefer_driver TEXT,
                    timeout_seconds INTEGER NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_idempotent_requests_created_at "
                "ON idempotent_requests(created_at_ms)"
            )
            conn.commit()

    def prune(self) -> int:
        cutoff_ms = int((time.time() - self.ttl_seconds) * 1000)
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM idempotent_requests WHERE created_at_ms < ?",
                    (cutoff_ms,),
                )
                conn.commit()
                return int(cur.rowcount or 0)

    def get(self, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT response_json FROM idempotent_requests WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["response_json"])
        except Exception:
            return None

    def put(
        self,
        request_id: str,
        *,
        command: str,
        args: dict[str, Any],
        backend: str,
        prefer_driver: str | None,
        timeout_seconds: int,
        response_payload: dict[str, Any],
    ) -> None:
        args_json = json.dumps(args, ensure_ascii=False, sort_keys=True)
        response_json = json.dumps(response_payload, ensure_ascii=False)
        created_at_ms = int(time.time() * 1000)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO idempotent_requests
                        (request_id, command, args_json, backend, prefer_driver, timeout_seconds, response_json, created_at_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        command,
                        args_json,
                        backend,
                        prefer_driver,
                        int(timeout_seconds),
                        response_json,
                        created_at_ms,
                    ),
                )
                conn.commit()
