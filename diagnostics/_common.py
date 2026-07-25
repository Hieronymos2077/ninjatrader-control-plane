"""Shared helpers for the nt8-api-control diagnostics suite.

Everything here is dynamic: it reads whatever runtime\\ actually contains at
import time or parse time, nothing is a hardcoded copy of an expected command
or action list. Keep it that way so this suite stays correct while WS-A, WS-B,
and WS-C edit runtime\\ in parallel.
"""
from __future__ import annotations

import ast
import gc
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / "runtime"
BACKENDS_DIR = RUNTIME_DIR / "backends"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

BACKEND_MODULE_PATHS: dict[str, Path] = {
    "file_write": BACKENDS_DIR / "file_write.py",
    "addon_http": BACKENDS_DIR / "addon_http.py",
    "dll_ati": BACKENDS_DIR / "dll_ati.py",
    "win32": BACKENDS_DIR / "win32_capture.py",
    "keyboard": BACKENDS_DIR / "keyboard.py",
}


class Result:
    def __init__(self, status: str, name: str, detail: str = "") -> None:
        self.status = status  # PASS, WARN, or FAIL
        self.name = name
        self.detail = detail

    def line(self) -> str:
        if self.detail:
            return f"[{self.status}] {self.name}: {self.detail}"
        return f"[{self.status}] {self.name}"


def report(results: list[Result], suite_name: str) -> int:
    """Print a table of results and return a process exit code.

    Exit code is 0 unless at least one result is FAIL.
    """
    passed = sum(1 for r in results if r.status == "PASS")
    warned = sum(1 for r in results if r.status == "WARN")
    failed = sum(1 for r in results if r.status == "FAIL")

    print(f"== {suite_name} ==")
    for r in results:
        print(r.line())
    print(f"=== {suite_name} summary: {passed} passed, {warned} warned, {failed} failed ===")
    return 1 if failed > 0 else 0


def extract_named_dict_keys(module_path: Path, var_name: str) -> set[str]:
    """Statically extract the string keys of `var_name = {...}` anywhere in a module.

    Used to introspect a backend's action dispatch table, or __main__.py's
    backend registry, without importing or executing anything that could send
    real keystrokes, hit the network, or touch a real device.
    """
    if not module_path.exists():
        return set()
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == var_name:
                    for key_node in node.value.keys:
                        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                            keys.add(key_node.value)
    return keys


def extract_backend_dispatch_keys(backend_name: str) -> set[str]:
    module_path = BACKEND_MODULE_PATHS.get(backend_name)
    if module_path is None:
        return set()
    return extract_named_dict_keys(module_path, "dispatch")


def extract_main_backend_names() -> set[str]:
    return extract_named_dict_keys(RUNTIME_DIR / "__main__.py", "backends")


def make_temp_nt8_dir() -> Path:
    """Create a TEMP directory shaped like a real NinjaTrader 8 data dir.

    Never touches the user's real Documents\\NinjaTrader 8. Caller owns cleanup
    via cleanup_temp_dir.
    """
    base = Path(tempfile.mkdtemp(prefix="nt8_diag_"))
    for sub in (
        "bin/Custom/Strategies",
        "bin/Custom/Indicators",
        "bin/Custom/AddOns",
        "bin/Custom/DrawingTools",
        "log",
        "trace",
        "strategyanalyzerlogs",
        "incoming",
        "outgoing",
    ):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def cleanup_temp_dir(path: Path) -> None:
    """Remove a TEMP directory, tolerating Windows file locks on sqlite files.

    runtime\\lifecycle.py and runtime\\idempotency.py open a fresh
    sqlite3.connect() per call and rely on garbage collection to close it,
    they never call conn.close() explicitly. On Windows that can leave the
    .db file locked for a moment right after server shutdown, so retry a
    few times instead of silently leaving a leftover TEMP directory behind.
    """
    gc.collect()
    for attempt in range(5):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(0.3)
    shutil.rmtree(path, ignore_errors=True)


def dump_text(value: Any) -> str:
    """Best effort flatten of a result payload to searchable text for substring checks."""
    import json

    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except Exception:
        return str(value)
