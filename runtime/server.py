from __future__ import annotations

import json
import threading
import time
import uuid
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

try:
    from .backends.base import ExecutionResult
    from .contracts import ALLOWED_RESPONSE_MODES, ALLOWED_TIMEOUT_PROFILES, ALLOWED_VERIFY_MODES, CommandEnvelopeV2, ERROR_CODES
    from .evidence import EvidenceStore, utc_timestamp_token
    from .idempotency import NT8IdempotencyStore
    from .lifecycle import CommandLifecycleStore
except ImportError:
    from backends.base import ExecutionResult
    from contracts import ALLOWED_RESPONSE_MODES, ALLOWED_TIMEOUT_PROFILES, ALLOWED_VERIFY_MODES, CommandEnvelopeV2, ERROR_CODES
    from evidence import EvidenceStore, utc_timestamp_token
    from idempotency import NT8IdempotencyStore
    from lifecycle import CommandLifecycleStore


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off"):
        return False
    return default


_TIMEOUT_PROFILE_FACTORS: dict[str, float] = {"fast": 0.6, "normal": 1.0, "slow": 1.5}

_COMMAND_TIMEOUT_BASE_SECONDS: dict[str, int] = {
    "read_only": 15,
    "chart_runtime": 25,
    "lifecycle": 45,
    "trade": 60,
    "bulk": 90,
    "compile": 60,
    "macro": 120,
    "default": 30,
}

_COMMAND_FAST_FAIL_BASE_SECONDS: dict[str, int] = {
    "read_only": 3,
    "chart_runtime": 4,
    "lifecycle": 5,
    "trade": 5,
    "bulk": 5,
    "compile": 8,
    "macro": 10,
    "default": 4,
}


class NT8ApiServer:
    """Local HTTP API for NT8 command execution.

    Endpoints:
    - GET  /v1/nt8/health
    - GET  /v1/nt8/catalog
    - GET  /v1/nt8/capabilities
    - GET  /v1/nt8/shortcuts
    - GET  /v1/nt8/metrics
    - GET  /v1/nt8/errors
    - GET  /v1/nt8/evidence?run_id=<id>&limit=100
    - POST /v1/nt8/command
    - POST /v1/nt8/command/batch
    """

    def __init__(
        self,
        control_plane: Any,
        *,
        host: str = "127.0.0.1",
        port: int = 8088,
        token: str | None = None,
        idempotency_store: NT8IdempotencyStore | None = None,
        idempotency_ttl_seconds: int = 24 * 3600,
    ) -> None:
        self.control_plane = control_plane
        self.host = host
        self.port = int(port)
        self.token = token
        state_dir = getattr(control_plane, "state_dir", Path.cwd() / ".nt8skill" / "state")
        workspace = getattr(control_plane, "workspace", Path.cwd())

        store = idempotency_store
        if store is None:
            store = NT8IdempotencyStore(Path(state_dir) / "idempotency.db", ttl_seconds=idempotency_ttl_seconds)
        self.idempotency_store = store
        self.lifecycle_store = CommandLifecycleStore(Path(state_dir) / "lifecycle.db")
        self.evidence_store = EvidenceStore(Path(workspace))

        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._evidence_counter = 0
        self._counter_lock = threading.Lock()

    @staticmethod
    def _json_safe(value: Any) -> Any:
        """Coerce a value into something JSON serializable and deep copyable.
        Backends touch the Win32 API and can leak ctypes handles into metadata;
        those cannot be pickled or JSON encoded, so a raw one would crash the
        request. This keeps the response robust no matter what a backend returns."""
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, dict):
            return {str(k): NT8ApiServer._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [NT8ApiServer._json_safe(v) for v in value]
        return str(value)

    @staticmethod
    def _result_to_json(result: ExecutionResult) -> dict[str, Any]:
        return {
            "success": bool(result.success),
            "driver": result.driver,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "artifacts": [str(p) for p in result.artifacts],
            "metadata": NT8ApiServer._json_safe(result.metadata),
        }

    @staticmethod
    def _apply_response_mode(
        *,
        result_payload: dict[str, Any],
        response_mode: str,
        return_fields: list[str] | None,
    ) -> dict[str, Any]:
        mode = str(response_mode or "normal")
        if mode not in ALLOWED_RESPONSE_MODES:
            mode = "normal"

        payload = deepcopy(result_payload)
        if return_fields:
            metadata = payload.get("metadata")
            if isinstance(metadata, dict):
                payload["metadata"] = {k: metadata[k] for k in return_fields if k in metadata}

        if mode == "compact":
            return {
                "success": bool(payload.get("success")),
                "driver": payload.get("driver"),
                "artifacts": payload.get("artifacts", []),
                "metadata": payload.get("metadata", {}),
            }
        if mode == "diagnostic":
            payload["diagnostic"] = {
                "stdout_len": len(str(payload.get("stdout", ""))),
                "stderr_len": len(str(payload.get("stderr", ""))),
            }
            return payload
        return payload

    @staticmethod
    def _map_error_code(*, stderr: str, contradiction: bool, unknown_command: bool = False, validation: bool = False) -> str:
        text = str(stderr or "").lower()
        if contradiction:
            return ERROR_CODES["verification_failed"]
        if unknown_command:
            return ERROR_CODES["unknown_command"]
        if validation:
            return ERROR_CODES["validation"]
        if "does not support backend" in text:
            return ERROR_CODES["backend_unsupported"]
        if "not supported via file" in text or "use the addon_http backend" in text:
            return ERROR_CODES["addon_timeout"]
        if "not supported by platform" in text or "not_supported_by_platform" in text or "platform gap" in text:
            return ERROR_CODES["not_supported_by_platform"]
        if "editor not open" in text or "could not focus ninjascript editor" in text or "editor_not_open" in text:
            return ERROR_CODES["editor_not_open"]
        if "analyzer not open" in text or "analyzer_not_open" in text or "strategy analyzer" in text and "not found" in text:
            return ERROR_CODES["analyzer_not_open"]
        if "addon version mismatch" in text or "addon_stale" in text:
            return ERROR_CODES["addon_stale"]
        if "addon" in text and "timeout" in text:
            return ERROR_CODES["addon_timeout"]
        if "addon unavailable" in text or "addon heartbeat stale" in text:
            return ERROR_CODES["addon_timeout"]
        if "compile_no_new_assembly" in text or "no new ninjatrader.custom.dll" in text:
            return ERROR_CODES["compile_no_new_assembly"]
        if "compile" in text and "timeout" in text:
            return ERROR_CODES["compile_timeout"]
        if "compile" in text and ("fail" in text or "error" in text):
            return ERROR_CODES["compile_failed"]
        if "timeout" in text:
            return ERROR_CODES["timeout"]
        if "symbol" in text and "not found" in text:
            return ERROR_CODES["symbol_not_found"]
        if "trade guard" in text or "live trading blocked" in text:
            return ERROR_CODES["trade_guard"]
        if "trade" in text and ("reject" in text or "failed" in text):
            return ERROR_CODES["trade_rejected"]
        if "nt8" in text and ("unavailable" in text or "not running" in text):
            return ERROR_CODES["nt8_unavailable"]
        if not text:
            return ERROR_CODES["ok"]
        return ERROR_CODES["internal"]

    @staticmethod
    def _is_retryable(*, error_code: str, stderr: str) -> bool:
        text = str(stderr or "").lower()
        if error_code in (
            ERROR_CODES["timeout"],
            ERROR_CODES["addon_timeout"],
            ERROR_CODES["nt8_unavailable"],
            ERROR_CODES["compile_timeout"],
        ):
            return True
        if "temporary" in text or "try again" in text or "unavailable" in text:
            return True
        return False

    @staticmethod
    def _classify_command(command: str) -> str:
        cmd = str(command or "").strip().lower()
        if cmd.startswith("trade."):
            return "trade"
        if cmd.startswith("compile."):
            return "compile"
        if cmd.startswith("macro."):
            return "macro"
        if cmd in (
            "strategy.attach",
            "strategy.detach",
            "bridge.deploy",
            "terminal.launch",
        ):
            return "lifecycle"
        if cmd in ("trade.flatten_all",):
            return "bulk"
        if cmd.startswith("chart.") or cmd.startswith("tester."):
            return "chart_runtime"
        if cmd.startswith("logs.") or cmd.startswith("account.") or cmd.startswith("position.") or cmd.startswith("order.") or cmd.startswith("market_data.") or cmd in (
            "terminal.detect",
            "bridge.status",
            "code.read",
            "code.list",
            "code.search",
        ):
            return "read_only"
        return "default"

    @staticmethod
    def _default_timeout_seconds(*, command: str, timeout_profile: str) -> int:
        command_class = NT8ApiServer._classify_command(command)
        base = int(_COMMAND_TIMEOUT_BASE_SECONDS.get(command_class, _COMMAND_TIMEOUT_BASE_SECONDS["default"]))
        factor = float(_TIMEOUT_PROFILE_FACTORS.get(timeout_profile, _TIMEOUT_PROFILE_FACTORS["normal"]))
        return max(1, int(round(base * factor)))

    @staticmethod
    def _default_fast_fail_seconds(*, command: str, timeout_profile: str, timeout_seconds: int) -> int:
        command_class = NT8ApiServer._classify_command(command)
        base = int(_COMMAND_FAST_FAIL_BASE_SECONDS.get(command_class, _COMMAND_FAST_FAIL_BASE_SECONDS["default"]))
        if timeout_profile == "slow":
            base += 1
        if timeout_profile == "fast":
            base = max(2, base - 1)
        return max(1, min(base, int(max(1, timeout_seconds))))

    @staticmethod
    def _extract_stage(result: ExecutionResult) -> str | None:
        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        for key in ("stage", "failure_stage", "execution_stage"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _extract_failure_signal(result: ExecutionResult, *, contradiction: bool) -> str | None:
        if contradiction:
            return "VISUAL_CONTRADICTION"
        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        for key in ("failure_signal", "hard_failure_signal", "signal"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        text = str(result.stderr or "").lower()
        if "addon heartbeat stale" in text:
            return "HARD_ADDON_HEARTBEAT_STALE"
        if "addon unavailable" in text:
            return "HARD_ADDON_UNAVAILABLE"
        if "does not support backend" in text:
            return "HARD_BACKEND_UNSUPPORTED"
        if "missing required args" in text or "requires non-empty" in text:
            return "HARD_VALIDATION"
        if "unknown nt8 command" in text:
            return "HARD_UNKNOWN_COMMAND"
        if "compile" in text and ("fail" in text or "error" in text):
            return "HARD_COMPILE_FAILED"
        if "timeout" in text:
            return "SOFT_TIMEOUT"
        return None

    @staticmethod
    def _extract_diagnostics(result: ExecutionResult) -> dict[str, Any]:
        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        diagnostics: dict[str, Any] = {}
        for key in ("diagnostics", "addon_runtime", "attach_workflow", "attach_attempts", "route_notes"):
            if key in metadata:
                diagnostics[key] = metadata.get(key)
        return diagnostics

    @staticmethod
    def _is_hard_failure_signal(*, error_code: str, failure_signal: str | None, stderr: str) -> bool:
        signal = str(failure_signal or "").upper()
        if signal.startswith("HARD_") or signal in (
            "VISUAL_CONTRADICTION",
            "HARD_VALIDATION",
            "HARD_UNKNOWN_COMMAND",
            "HARD_BACKEND_UNSUPPORTED",
            "HARD_COMPILE_FAILED",
        ):
            return True
        if error_code in (
            ERROR_CODES["validation"],
            ERROR_CODES["unknown_command"],
            ERROR_CODES["backend_unsupported"],
            ERROR_CODES["compile_failed"],
            ERROR_CODES["trade_guard"],
            ERROR_CODES["trade_rejected"],
            ERROR_CODES["verification_failed"],
            ERROR_CODES["not_supported_by_platform"],
        ):
            return True
        text = str(stderr or "").lower()
        if "missing required args" in text or "does not support backend" in text:
            return True
        return False

    def _next_command_index(self) -> int:
        with self._counter_lock:
            self._evidence_counter += 1
            return self._evidence_counter

    def _build_envelope(self, payload: dict[str, Any]) -> tuple[CommandEnvelopeV2 | None, str | None]:
        if not isinstance(payload, dict):
            return None, "payload must be a JSON object"

        command = payload.get("command")
        if not isinstance(command, str) or not command.strip():
            return None, "field 'command' is required"

        args = payload.get("args", {})
        if not isinstance(args, dict):
            return None, "field 'args' must be an object when provided"

        if "evidence" in payload and isinstance(payload["evidence"], dict):
            args = dict(args)
            args["_evidence_context"] = dict(payload["evidence"])

        request_id = payload.get("request_id")
        if request_id is not None and not isinstance(request_id, str):
            return None, "field 'request_id' must be a string"

        response_mode = str(payload.get("response_mode", "normal"))
        if response_mode not in ALLOWED_RESPONSE_MODES:
            return None, f"field 'response_mode' must be one of {sorted(ALLOWED_RESPONSE_MODES)}"

        verify_mode = str(payload.get("verify_mode", "none"))
        if verify_mode not in ALLOWED_VERIFY_MODES:
            return None, f"field 'verify_mode' must be one of {sorted(ALLOWED_VERIFY_MODES)}"

        timeout_profile = str(payload.get("timeout_profile", "normal")).strip().lower() or "normal"
        if timeout_profile not in ALLOWED_TIMEOUT_PROFILES:
            return None, f"field 'timeout_profile' must be one of {sorted(ALLOWED_TIMEOUT_PROFILES)}"

        command_name = command.strip()
        default_timeout = self._default_timeout_seconds(command=command_name, timeout_profile=timeout_profile)
        if "timeout_seconds" in payload:
            timeout_seconds = max(1, _as_int(payload.get("timeout_seconds"), default_timeout))
        else:
            timeout_seconds = default_timeout

        default_fast_fail = self._default_fast_fail_seconds(
            command=command_name,
            timeout_profile=timeout_profile,
            timeout_seconds=timeout_seconds,
        )
        if "fast_fail_seconds" in payload:
            fast_fail_seconds = max(1, min(_as_int(payload.get("fast_fail_seconds"), default_fast_fail), timeout_seconds))
        else:
            fast_fail_seconds = default_fast_fail

        return_fields = payload.get("return_fields")
        if return_fields is not None:
            if not isinstance(return_fields, list) or not all(isinstance(item, str) for item in return_fields):
                return None, "field 'return_fields' must be a list of strings when provided"

        risk_context = payload.get("risk_context")
        if risk_context is not None and not isinstance(risk_context, dict):
            return None, "field 'risk_context' must be an object when provided"

        envelope = CommandEnvelopeV2(
            command=command_name,
            args=args,
            backend=str(payload.get("backend", "auto")),
            prefer_driver=payload.get("prefer_driver"),
            timeout_seconds=timeout_seconds,
            timeout_profile=timeout_profile,  # type: ignore[arg-type]
            fast_fail_seconds=fast_fail_seconds,
            request_id=request_id,
            trace_id=payload.get("trace_id"),
            instance_id=payload.get("instance_id"),
            response_mode=response_mode,  # type: ignore[arg-type]
            verify_mode=verify_mode,  # type: ignore[arg-type]
            risk_context=risk_context,
            return_fields=return_fields,
            max_retries=max(0, min(_as_int(payload.get("max_retries", 0), 0), 5)),
        )
        return envelope, None

    def _run_visual_verification(self, envelope: CommandEnvelopeV2, result: ExecutionResult) -> dict[str, Any]:
        mode = str(envelope.verify_mode)
        api_passed = bool(result.success)
        verification: dict[str, Any] = {
            "mode": mode,
            "performed": False,
            "api_passed": api_passed,
            "visual_passed": None,
            "passed": api_passed,
            "assertions": [],
            "contradiction": False,
        }

        if mode in ("none", "api"):
            return verification

        verifier = getattr(self.control_plane, "perform_visual_verification", None)
        if not callable(verifier):
            verification.update(
                {
                    "performed": True,
                    "visual_passed": False,
                    "passed": False,
                    "reason": "control plane visual verifier unavailable",
                }
            )
            return verification

        try:
            visual = verifier(
                command=envelope.command,
                args=envelope.args,
                result=result,
                verify_mode=mode,
                trace_id=envelope.trace_id,
                instance_id=envelope.instance_id,
            )
        except Exception as exc:
            visual = {"performed": True, "passed": False, "assertions": [], "reason": str(exc)}

        visual_passed = bool(visual.get("passed", False))
        performed = bool(visual.get("performed", True))
        verification.update(
            {
                "performed": performed,
                "visual_passed": visual_passed,
                "assertions": visual.get("assertions", []),
                "visual": visual,
                "passed": bool(api_passed and visual_passed),
                "contradiction": bool(api_passed and performed and not visual_passed),
            }
        )
        return verification

    def _execute_envelope(self, envelope: CommandEnvelopeV2) -> dict[str, Any]:
        cmd_id = envelope.request_id or uuid.uuid4().hex
        total_start = time.perf_counter()
        self.lifecycle_store.create_command(
            cmd_id=cmd_id,
            request_id=envelope.request_id,
            trace_id=envelope.trace_id,
            instance_id=envelope.instance_id,
            command=envelope.command,
        )
        self.lifecycle_store.transition(cmd_id=cmd_id, state="queued", message="accepted")

        result = ExecutionResult(success=False, driver="nt8", stderr="command did not run")
        verification: dict[str, Any] = {
            "mode": str(envelope.verify_mode),
            "performed": False,
            "api_passed": False,
            "visual_passed": None,
            "passed": False,
            "assertions": [],
            "contradiction": False,
        }
        execution_ms_total = 0.0
        verification_ms_total = 0.0
        retryable = False
        error_code = ERROR_CODES["internal"]
        attempts = 0
        stage: str | None = None
        failure_signal: str | None = None
        fast_fail_triggered = False
        diagnostics: dict[str, Any] = {}

        for attempt in range(envelope.max_retries + 1):
            attempts = attempt + 1
            self.lifecycle_store.transition(cmd_id=cmd_id, state="sent", message=f"attempt={attempts}")

            exec_start = time.perf_counter()
            try:
                command_args = dict(envelope.args)
                command_args.setdefault("_timeout_profile", str(envelope.timeout_profile))
                if envelope.fast_fail_seconds is not None:
                    command_args.setdefault("_fast_fail_seconds", int(envelope.fast_fail_seconds))
                result = self.control_plane.run_command(
                    command=envelope.command,
                    args=command_args,
                    backend=str(envelope.backend),
                    timeout_seconds=int(envelope.timeout_seconds),
                )
            except Exception as exc:
                result = ExecutionResult(
                    success=False,
                    driver="nt8",
                    stderr=f"run_command exception: {exc}",
                    metadata={"exception": str(exc)},
                )
            execution_ms_total += (time.perf_counter() - exec_start) * 1000.0

            verify_start = time.perf_counter()
            verification = self._run_visual_verification(envelope, result)
            verification_ms_total += (time.perf_counter() - verify_start) * 1000.0

            contradiction = bool(verification.get("contradiction"))
            if contradiction:
                result.success = False
                message = "visual contradiction: command succeeded via API but failed visual assertions"
                result.stderr = f"{result.stderr} | {message}" if result.stderr else message

            error_code = self._map_error_code(
                stderr=result.stderr,
                contradiction=contradiction,
                unknown_command=("unknown nt8 command" in str(result.stderr).lower()),
                validation=(
                    "missing required args" in str(result.stderr).lower()
                    or "requires non-empty" in str(result.stderr).lower()
                ),
            )
            retryable = self._is_retryable(error_code=error_code, stderr=result.stderr)
            stage = self._extract_stage(result)
            failure_signal = self._extract_failure_signal(result, contradiction=contradiction)
            diagnostics = self._extract_diagnostics(result)
            hard_signal = self._is_hard_failure_signal(
                error_code=error_code,
                failure_signal=failure_signal,
                stderr=result.stderr,
            )
            if hard_signal:
                retryable = False
                fast_fail_triggered = True

            self.lifecycle_store.transition(
                cmd_id=cmd_id,
                state="verified",
                message="verification complete",
                error_code=None if result.success else error_code,
                retryable=retryable,
                payload={
                    "verification": verification,
                    "driver": result.driver,
                    "stage": stage,
                    "failure_signal": failure_signal,
                    "hard_signal": hard_signal,
                    "fast_fail_seconds": envelope.fast_fail_seconds,
                },
            )

            if result.success:
                break
            if hard_signal:
                break
            if attempt >= envelope.max_retries or not retryable:
                break
            time.sleep(0.15 * float(attempt + 1))

        final_state = "done" if result.success else "failed"
        self.lifecycle_store.transition(
            cmd_id=cmd_id,
            state=final_state,
            message="completed",
            error_code=None if result.success else error_code,
            retryable=retryable,
            payload={"attempts": attempts},
        )
        if not result.success:
            self.lifecycle_store.add_dead_letter(
                cmd_id=cmd_id,
                reason=str(error_code),
                payload={"command": envelope.command, "stderr": result.stderr, "verification": verification},
            )

        timing = {
            "attempts": attempts,
            "execution_ms": round(execution_ms_total, 3),
            "verification_ms": round(verification_ms_total, 3),
            "total_ms": round((time.perf_counter() - total_start) * 1000.0, 3),
        }
        result_payload = self._apply_response_mode(
            result_payload=self._result_to_json(result),
            response_mode=str(envelope.response_mode),
            return_fields=envelope.return_fields,
        )

        evidence_context = envelope.args.get("_evidence_context")
        if not isinstance(evidence_context, dict):
            evidence_context = {}
        round_name = str(evidence_context.get("round", "adhoc"))
        feature = str(evidence_context.get("feature", envelope.command.replace(".", "_")))
        timestamp = str(evidence_context.get("timestamp", utc_timestamp_token()))
        default_command_index = self._next_command_index()
        command_index = _as_int(evidence_context.get("command_index", default_command_index), default_command_index)
        evidence = self.evidence_store.record_command(
            round_name=round_name,
            feature=feature,
            timestamp=timestamp,
            command_index=command_index,
            command=envelope.command,
            backend=str(envelope.backend),
            args=envelope.args,
            request_id=envelope.request_id,
            trace_id=envelope.trace_id,
            instance_id=envelope.instance_id,
            result_payload=result_payload,
            verification=verification,
            timing=timing,
            error_code=error_code,
            retryable=retryable,
            attempts=attempts,
            notes=[
                f"response_mode={envelope.response_mode}",
                f"verify_mode={envelope.verify_mode}",
                f"timeout_profile={envelope.timeout_profile}",
                f"fast_fail_seconds={envelope.fast_fail_seconds}",
            ],
        )
        verification["evidence"] = evidence

        return {
            "ok": bool(result.success),
            "request_id": envelope.request_id,
            "trace_id": envelope.trace_id,
            "result": result_payload,
            "verification": verification,
            "timing": timing,
            "error_code": ERROR_CODES["ok"] if result.success else error_code,
            "retryable": bool(retryable and not result.success),
            "idempotent_replay": False,
            "stage": stage,
            "failure_signal": failure_signal,
            "fast_fail_triggered": bool(fast_fail_triggered),
            "timeout_profile": str(envelope.timeout_profile),
            "fast_fail_seconds": envelope.fast_fail_seconds,
            "diagnostics": diagnostics,
        }

    def handle_command_payload(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        envelope, error = self._build_envelope(payload)
        if error:
            return 400, {"ok": False, "error": error, "error_code": ERROR_CODES["validation"]}
        if envelope is None:
            return 400, {"ok": False, "error": "invalid payload", "error_code": ERROR_CODES["validation"]}

        if envelope.request_id:
            cached = self.idempotency_store.get(envelope.request_id)
            if cached is not None:
                replay = deepcopy(cached)
                replay["idempotent_replay"] = True
                return 200, replay

        response = self._execute_envelope(envelope)
        if envelope.request_id:
            self.idempotency_store.put(
                envelope.request_id,
                command=envelope.command,
                args=envelope.args,
                backend=str(envelope.backend),
                prefer_driver=envelope.prefer_driver,
                timeout_seconds=int(envelope.timeout_seconds),
                response_payload=response,
            )
        return 200, response

    def handle_batch_payload(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if not isinstance(payload, dict):
            return 400, {"ok": False, "error": "payload must be an object"}
        commands = payload.get("commands")
        if not isinstance(commands, list) or not commands:
            return 400, {"ok": False, "error": "field 'commands' must be a non-empty list"}
        stop_on_error = _coerce_bool(payload.get("stop_on_error"), default=False)

        items: list[dict[str, Any]] = []
        for item in commands:
            status, response = self.handle_command_payload(item if isinstance(item, dict) else {})
            items.append({"status": status, "response": response})
            if stop_on_error and (status != 200 or not bool(response.get("ok"))):
                break

        failures = [i for i in items if i.get("status") != 200 or not bool((i.get("response") or {}).get("ok"))]
        return 200, {
            "ok": len(failures) == 0,
            "results": items,
            "count": len(items),
            "failed_count": len(failures),
        }

    def _is_authorized(self, handler: BaseHTTPRequestHandler) -> bool:
        if not self.token:
            return True
        supplied = handler.headers.get("X-NT8-Token", "")
        if supplied == self.token:
            return True
        auth = handler.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth.removeprefix("Bearer ").strip() == self.token:
            return True
        return False

    @staticmethod
    def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any] | None:
        try:
            content_len = int(handler.headers.get("Content-Length", "0"))
        except Exception:
            content_len = 0
        if content_len <= 0:
            return {}
        raw = handler.rfile.read(content_len)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    @staticmethod
    def _write_json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                _ = fmt, args

            def _unauthorized(self) -> None:
                server._write_json(self, 401, {"ok": False, "error": "unauthorized"})

            def do_GET(self) -> None:  # noqa: N802
                if not server._is_authorized(self):
                    self._unauthorized()
                    return

                parsed = urlparse(self.path)
                path = parsed.path
                query = parse_qs(parsed.query or "")

                if path == "/v1/nt8/health":
                    payload = server.control_plane.health_check()
                    server._write_json(self, 200, {"ok": True, "payload": payload})
                    return

                if path == "/v1/nt8/catalog":
                    server._write_json(self, 200, {"ok": True, "payload": server.control_plane.command_catalog()})
                    return

                if path == "/v1/nt8/capabilities":
                    server._write_json(self, 200, {"ok": True, "payload": server.control_plane.command_capabilities()})
                    return

                if path == "/v1/nt8/shortcuts":
                    server._write_json(self, 200, {"ok": True, "payload": server.control_plane.shortcuts()})
                    return

                if path == "/v1/nt8/metrics":
                    since_seconds = _as_int(query.get("since_seconds", ["3600"])[0], 3600)
                    server._write_json(self, 200, {"ok": True, "payload": server.lifecycle_store.metrics(since_seconds=since_seconds)})
                    return

                if path == "/v1/nt8/errors":
                    limit = _as_int(query.get("limit", ["50"])[0], 50)
                    server._write_json(self, 200, {"ok": True, "payload": server.lifecycle_store.recent_errors(limit=limit)})
                    return

                if path == "/v1/nt8/evidence":
                    run_id = query.get("run_id", [None])[0]
                    limit = _as_int(query.get("limit", ["100"])[0], 100)
                    payload = server.evidence_store.list_evidence(run_id=run_id, limit=limit)
                    server._write_json(self, 200, {"ok": True, "payload": payload})
                    return

                server._write_json(self, 404, {"ok": False, "error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                if not server._is_authorized(self):
                    self._unauthorized()
                    return

                parsed = urlparse(self.path)
                payload = server._read_json_body(self)
                if payload is None:
                    server._write_json(self, 400, {"ok": False, "error": "invalid JSON body"})
                    return

                if parsed.path == "/v1/nt8/command":
                    status, response = server.handle_command_payload(payload)
                    server._write_json(self, status, response)
                    return

                if parsed.path == "/v1/nt8/command/batch":
                    status, response = server.handle_batch_payload(payload)
                    server._write_json(self, status, response)
                    return

                server._write_json(self, 404, {"ok": False, "error": "not found"})

        return Handler

    def serve_forever(self) -> None:
        self.idempotency_store.prune()
        self._httpd = ThreadingHTTPServer((self.host, self.port), self._make_handler())
        self._httpd.serve_forever()

    def start_background(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        def _runner() -> None:
            self.serve_forever()

        self._thread = threading.Thread(target=_runner, daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
