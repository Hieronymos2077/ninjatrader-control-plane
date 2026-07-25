from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path


@dataclass
class ExecutionResult:
    success: bool
    driver: str = "nt8"
    stdout: str = ""
    stderr: str = ""
    artifacts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BackendBase:
    name: str = "base"

    def is_available(self) -> bool:
        return False

    def execute(self, action: str, args: dict[str, Any]) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            stderr=f"Backend {self.name} does not implement action '{action}'",
        )
