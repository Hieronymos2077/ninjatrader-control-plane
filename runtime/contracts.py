from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ResponseMode = Literal["compact", "normal", "diagnostic"]
VerifyMode = Literal["none", "api", "visual", "api+visual"]
TimeoutProfile = Literal["fast", "normal", "slow"]


ALLOWED_RESPONSE_MODES: set[str] = {"compact", "normal", "diagnostic"}
ALLOWED_VERIFY_MODES: set[str] = {"none", "api", "visual", "api+visual"}
ALLOWED_TIMEOUT_PROFILES: set[str] = {"fast", "normal", "slow"}


ERROR_CODES: dict[str, str] = {
    "ok": "OK",
    "validation": "ERR_VALIDATION",
    "unknown_command": "ERR_UNKNOWN_COMMAND",
    "backend_unsupported": "ERR_BACKEND_UNSUPPORTED",
    "timeout": "ERR_TIMEOUT",
    "addon_timeout": "ERR_ADDON_TIMEOUT",
    "nt8_unavailable": "ERR_NT8_UNAVAILABLE",
    "compile_failed": "ERR_COMPILE_FAILED",
    "symbol_not_found": "ERR_SYMBOL_NOT_FOUND",
    "trade_guard": "ERR_TRADE_GUARD",
    "trade_rejected": "ERR_TRADE_REJECTED",
    "verification_failed": "ERR_VERIFICATION_FAILED",
    "internal": "ERR_INTERNAL",
    "editor_not_open": "ERR_EDITOR_NOT_OPEN",
    "analyzer_not_open": "ERR_ANALYZER_NOT_OPEN",
    "compile_timeout": "ERR_COMPILE_TIMEOUT",
    "compile_no_new_assembly": "ERR_COMPILE_NO_NEW_ASSEMBLY",
    "not_supported_by_platform": "ERR_NOT_SUPPORTED_BY_PLATFORM",
    "addon_stale": "ERR_ADDON_STALE",
}


@dataclass(slots=True)
class CommandEnvelopeV2:
    command: str
    args: dict[str, Any] = field(default_factory=dict)
    backend: str = "auto"
    prefer_driver: str | None = None
    timeout_seconds: int = 120
    timeout_profile: TimeoutProfile = "normal"
    fast_fail_seconds: int | None = None
    request_id: str | None = None
    trace_id: str | None = None
    instance_id: str | None = None
    response_mode: ResponseMode = "normal"
    verify_mode: VerifyMode = "none"
    risk_context: dict[str, Any] | None = None
    return_fields: list[str] | None = None
    max_retries: int = 0
