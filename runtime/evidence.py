from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANIFEST_SCHEMA_ID = "nt8.visual.evidence.manifest.v1"


def _evidence_enabled() -> bool:
    return os.environ.get("NT8_EVIDENCE", "on").strip().lower() not in ("off", "0", "false", "no")


def utc_timestamp_token() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip())
    cleaned = cleaned.strip("_")
    return cleaned or "item"


def evidence_manifest_template() -> dict[str, Any]:
    return {
        "schema_id": MANIFEST_SCHEMA_ID,
        "generated_at_utc": "",
        "run_id": "",
        "round": "",
        "feature": "",
        "timestamp": "",
        "request_id": None,
        "trace_id": None,
        "instance_id": None,
        "command": "",
        "backend": "auto",
        "args": {},
        "result": {},
        "verification": {},
        "timing": {},
        "error_code": "",
        "retryable": False,
        "attempts": 1,
        "artifacts": [],
        "notes": [],
    }


class EvidenceStore:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.base_dir = self.workspace / "captures" / "validation_runs"
        self.enabled = _evidence_enabled()
        if self.enabled:
            self.base_dir.mkdir(parents=True, exist_ok=True)

    def build_run_id(self, *, round_name: str, timestamp: str) -> str:
        return f"{_slug(round_name)}-{_slug(timestamp)}"

    def run_dir(self, *, round_name: str, feature: str, timestamp: str) -> Path:
        target = self.base_dir / _slug(round_name) / _slug(feature) / _slug(timestamp)
        target.mkdir(parents=True, exist_ok=True)
        return target

    def record_command(
        self,
        *,
        round_name: str,
        feature: str,
        timestamp: str,
        command_index: int,
        command: str,
        backend: str,
        args: dict[str, Any],
        request_id: str | None,
        trace_id: str | None,
        instance_id: str | None,
        result_payload: dict[str, Any],
        verification: dict[str, Any],
        timing: dict[str, Any],
        error_code: str,
        retryable: bool,
        attempts: int,
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {
                "enabled": False,
                "run_id": None,
                "run_dir": None,
                "manifest_path": None,
                "response_path": None,
                "round": round_name,
                "feature": feature,
                "timestamp": timestamp,
                "command_index": int(command_index),
            }

        run_id = self.build_run_id(round_name=round_name, timestamp=timestamp)
        run_dir = self.run_dir(round_name=round_name, feature=feature, timestamp=timestamp)
        prefix = f"{int(command_index):03d}_{_slug(command)}"

        manifest = evidence_manifest_template()
        manifest.update(
            {
                "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
                "run_id": run_id,
                "round": round_name,
                "feature": feature,
                "timestamp": timestamp,
                "request_id": request_id,
                "trace_id": trace_id,
                "instance_id": instance_id,
                "command": command,
                "backend": backend,
                "args": args,
                "result": result_payload,
                "verification": verification,
                "timing": timing,
                "error_code": error_code,
                "retryable": bool(retryable),
                "attempts": max(1, int(attempts)),
                "artifacts": result_payload.get("artifacts", []),
                "notes": list(notes or []),
            }
        )

        manifest_path = run_dir / f"{prefix}_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        response_path = run_dir / f"{prefix}_response.json"
        response_path.write_text(json.dumps(result_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "manifest_path": str(manifest_path),
            "response_path": str(response_path),
            "round": round_name,
            "feature": feature,
            "timestamp": timestamp,
            "command_index": int(command_index),
        }

    def write_round_summary(
        self,
        *,
        round_name: str,
        timestamp: str,
        summary: dict[str, Any],
    ) -> Path:
        round_dir = self.base_dir / _slug(round_name)
        round_dir.mkdir(parents=True, exist_ok=True)
        path = round_dir / f"round_summary_{_slug(timestamp)}.json"
        path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def write_gate_report(self, *, timestamp: str, report: dict[str, Any]) -> Path:
        path = self.base_dir / f"gate_report_{_slug(timestamp)}.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def list_evidence(self, *, run_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit), 1000))
        manifests = sorted(self.base_dir.rglob("*_manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        output: list[dict[str, Any]] = []
        for path in manifests:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if run_id and str(payload.get("run_id")) != run_id:
                continue
            output.append(
                {
                    "manifest_path": str(path),
                    "run_id": payload.get("run_id"),
                    "round": payload.get("round"),
                    "feature": payload.get("feature"),
                    "timestamp": payload.get("timestamp"),
                    "command": payload.get("command"),
                    "request_id": payload.get("request_id"),
                    "trace_id": payload.get("trace_id"),
                    "error_code": payload.get("error_code"),
                    "result_success": bool((payload.get("result") or {}).get("success")),
                    "verification_passed": bool((payload.get("verification") or {}).get("passed", True)),
                }
            )
            if len(output) >= lim:
                break
        return output
