"""WS A self test for the NT8 controller and server layer.

Owned by workstream WS A. Does not touch diagnostics (WS D owns that) and never
touches C:\\Users\\<you>\\Documents\\NinjaTrader 8. Runs entirely against TEMP
directories and a TEMP port.

Checks:
  a) controller and server modules import cleanly.
  b) every catalog command's action map entry names only actions that are
     either already present in the live backend dispatch tables, or listed as
     a new action in CONTRACT.md (tolerated as a WARN, since WS B and WS C add
     those in parallel). Any other action name is a FAIL (invented name, real bug).
  c) the control plane instantiates against a TEMP workspace and a TEMP fake
     nt8_data_dir.
  d) the HTTP server boots on a TEMP port and answers health, catalog, and
     capabilities with valid JSON.

Run with:
  .venv\\Scripts\\python.exe runtime\\selftest_ws_a.py
"""
from __future__ import annotations

import inspect
import json
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

RESULTS: list[tuple[str, str, str]] = []  # (level, check, message)


def record(level: str, check: str, message: str = "") -> None:
    RESULTS.append((level, check, message))
    print(f"[{level}] {check}" + (f": {message}" if message else ""))


# ── (a) imports ──────────────────────────────────────────────────────────
try:
    import controller
    import server as server_module
    from backends.file_write import FileWriteBackend
    from backends.addon_http import AddonHttpBackend
    from backends.dll_ati import DllAtiBackend
    from backends.win32_capture import Win32CaptureBackend
    from backends.keyboard import KeyboardBackend

    record("PASS", "import controller and server modules")
except Exception as exc:
    record("FAIL", "import controller and server modules", str(exc))
    print("\nFATAL: cannot continue without imports.")
    sys.exit(1)


# ── (b) action map validation against live dispatch tables + CONTRACT.md ──

def _extract_dispatch_keys(execute_method) -> set[str]:
    """Extract the string keys of the `dispatch = {...}` dict literal inside
    a BackendBase.execute() method by bracket matching its source text. All
    backends in this repo follow the same `dispatch = { "action": self._x, ...}`
    pattern, so this avoids instantiating/running any real action."""
    source = inspect.getsource(execute_method)
    start = source.find("dispatch = {")
    if start == -1:
        return set()
    brace_start = source.find("{", start)
    depth = 0
    end = brace_start
    for idx in range(brace_start, len(source)):
        ch = source[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = idx
                break
    block = source[brace_start:end + 1]
    keys = set()
    for line in block.splitlines():
        line = line.strip()
        if line.startswith('"') and '":' in line:
            key = line.split('"', 2)[1]
            keys.add(key)
    return keys


LIVE_DISPATCH: dict[str, set[str]] = {
    "file_write": _extract_dispatch_keys(FileWriteBackend.execute),
    "addon_http": _extract_dispatch_keys(AddonHttpBackend.execute),
    "dll_ati": _extract_dispatch_keys(DllAtiBackend.execute),
    "win32": _extract_dispatch_keys(Win32CaptureBackend.execute),
    "keyboard": _extract_dispatch_keys(KeyboardBackend.execute),
}

for backend_name, keys in LIVE_DISPATCH.items():
    if keys:
        record("PASS", f"enumerate live dispatch keys for backend '{backend_name}'", f"{len(keys)} actions")
    else:
        record("FAIL", f"enumerate live dispatch keys for backend '{backend_name}'", "no dispatch keys found, extractor may be broken")

# Actions CONTRACT.md names as NEW (may not have landed yet from WS B / WS C).
CONTRACT_NEW_ACTIONS: dict[str, set[str]] = {
    "file_write": {"compile_status", "parse_compile_errors", "analyzer_status", "analyzer_results", "analyzer_list_results"},
    "keyboard": {"close_chart", "configure_tester", "start_tester", "compile"},
    "addon_http": {"get_account_info", "subscribe_market_data"},
    "dll_ati": set(),
    "win32": set(),
}

VALID_BACKEND_NAMES = {"file_write", "addon_http", "dll_ati", "win32", "keyboard", "auto"}

action_map_fail = 0
action_map_warn = 0
action_map_pass = 0

for cmd, entry in controller.NT8_COMMAND_CATALOG.items():
    for backend_name in entry.get("backends", []):
        if backend_name not in VALID_BACKEND_NAMES:
            record("FAIL", f"catalog '{cmd}' backends", f"unknown backend name '{backend_name}'")
            action_map_fail += 1

    action_entry = controller._BACKEND_ACTION_MAP.get(cmd, {})
    for backend_name, action_name in action_entry.items():
        if backend_name not in LIVE_DISPATCH:
            record("FAIL", f"action map '{cmd}' -> {backend_name}", f"unknown backend '{backend_name}'")
            action_map_fail += 1
            continue
        if action_name in LIVE_DISPATCH[backend_name]:
            action_map_pass += 1
            continue
        if action_name in CONTRACT_NEW_ACTIONS.get(backend_name, set()):
            record(
                "WARN",
                f"action map '{cmd}' -> {backend_name}:{action_name}",
                "listed as a new CONTRACT.md action, not yet present in this backend's live dispatch",
            )
            action_map_warn += 1
            continue
        record(
            "FAIL",
            f"action map '{cmd}' -> {backend_name}:{action_name}",
            "action name is neither in the live dispatch table nor in CONTRACT.md's new action list (invented name)",
        )
        action_map_fail += 1

record(
    "PASS" if action_map_fail == 0 else "FAIL",
    "action map validation summary",
    f"{action_map_pass} pass, {action_map_warn} warn (tolerated), {action_map_fail} fail",
)

# bridge.deploy must NOT have a dead action map entry (task 1: remove it).
if "bridge.deploy" in controller._BACKEND_ACTION_MAP:
    record("FAIL", "bridge.deploy action map entry removed", "still present, should be dead code removed")
else:
    record("PASS", "bridge.deploy action map entry removed")

# system.capabilities and macro.full_dev_cycle must exist in the catalog.
for required_cmd in ("tester.list_results", "system.capabilities", "macro.full_dev_cycle"):
    if required_cmd in controller.NT8_COMMAND_CATALOG:
        record("PASS", f"catalog contains new command '{required_cmd}'")
    else:
        record("FAIL", f"catalog contains new command '{required_cmd}'", "missing")


# ── (c) instantiate control plane against TEMP dirs ────────────────────────
temp_root = Path(tempfile.mkdtemp(prefix="nt8_selftest_"))
fake_nt8_data_dir = temp_root / "fake_nt8_data"
fake_nt8_data_dir.mkdir(parents=True, exist_ok=True)
workspace_dir = temp_root / "workspace"
workspace_dir.mkdir(parents=True, exist_ok=True)

try:
    backends = {
        "file_write": FileWriteBackend(nt8_data_dir=fake_nt8_data_dir),
        "addon_http": AddonHttpBackend(port=18099),  # unused test port, never a real addon
        "dll_ati": DllAtiBackend(nt8_data_dir=fake_nt8_data_dir),
        "win32": Win32CaptureBackend(),
        "keyboard": KeyboardBackend(),
    }
    cp = controller.NT8ControlPlane(nt8_data_dir=fake_nt8_data_dir, backends=backends, workspace=workspace_dir)
    record("PASS", "instantiate NT8ControlPlane against TEMP workspace and fake nt8_data_dir", str(temp_root))
except Exception as exc:
    record("FAIL", "instantiate NT8ControlPlane against TEMP workspace and fake nt8_data_dir", str(exc))
    print("\nFATAL: cannot continue without a control plane instance.")
    sys.exit(1)

try:
    caps = cp.command_capabilities()
    assert "commands" in caps and "backend_health" in caps
    assert "system.capabilities" in caps["commands"]
    record("PASS", "control_plane.command_capabilities() returns a well formed report")
except Exception as exc:
    record("FAIL", "control_plane.command_capabilities() returns a well formed report", str(exc))


# ── (d) boot HTTP server on TEMP port, hit health/catalog/capabilities ─────
TEST_PORT = 18088
srv = server_module.NT8ApiServer(control_plane=cp, port=TEST_PORT)

try:
    srv.start_background()
    time.sleep(0.5)

    def _get_json(path: str) -> tuple[int, dict]:
        req = urllib.request.Request(f"http://127.0.0.1:{TEST_PORT}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            body = json.loads(resp.read().decode("utf-8"))
            return status, body

    for path in ("/v1/nt8/health", "/v1/nt8/catalog", "/v1/nt8/capabilities"):
        try:
            status, body = _get_json(path)
            if status == 200 and isinstance(body, dict) and body.get("ok") is True:
                record("PASS", f"GET {path}", f"status={status}")
            else:
                record("FAIL", f"GET {path}", f"status={status} body_ok={body.get('ok') if isinstance(body, dict) else 'n/a'}")
        except Exception as exc:
            record("FAIL", f"GET {path}", str(exc))
finally:
    srv.shutdown()
    record("PASS", "server shutdown", "")


# ── summary ──────────────────────────────────────────────────────────────
fail_count = sum(1 for level, _, _ in RESULTS if level == "FAIL")
warn_count = sum(1 for level, _, _ in RESULTS if level == "WARN")
pass_count = sum(1 for level, _, _ in RESULTS if level == "PASS")

print(f"\nSUMMARY: {pass_count} pass, {warn_count} warn, {fail_count} fail")
if fail_count > 0:
    print("RESULT: FAIL")
    sys.exit(1)
print("RESULT: PASS")
sys.exit(0)
