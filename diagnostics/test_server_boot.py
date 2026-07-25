"""Boots the real NT8 API server against a TEMP workspace and TEMP fake NT8 data
dir, then exercises the HTTP surface. Never touches the user's real
Documents\\NinjaTrader 8, never launches or kills NinjaTrader or Chrome. The only
real world interaction is a process list scan via terminal.detect (win32 backend),
which is read only.

Run directly:
    python diagnostics\\test_server_boot.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import Result, cleanup_temp_dir, make_temp_nt8_dir, report  # noqa: E402


PORT = 18090


def _get(url: str, timeout: float = 8.0):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = resp.status
        body = resp.read()
    data = json.loads(body) if body else {}
    return status, data


def _get_tolerant(url: str, timeout: float = 8.0):
    try:
        return _get(url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}
        return exc.code, data


def _post(url: str, payload: dict, timeout: float = 15.0):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            resp_body = resp.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        resp_body = exc.read()
    data = json.loads(resp_body) if resp_body else {}
    return status, data


def _wait_for_server(base_url: str, timeout_seconds: float = 20.0) -> bool:
    # health_check() probes the addon_http backend's /health endpoint with its
    # own short timeout, and enumerates the Windows process list, so the very
    # first call after boot can take a few seconds. Give each attempt a
    # generous per call timeout so we do not abort a response mid write.
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            status, _ = _get(f"{base_url}/v1/nt8/health", timeout=6.0)
            if status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def main() -> int:
    from runtime.backends.addon_http import AddonHttpBackend
    from runtime.backends.dll_ati import DllAtiBackend
    from runtime.backends.file_write import FileWriteBackend
    from runtime.backends.keyboard import KeyboardBackend
    from runtime.backends.win32_capture import Win32CaptureBackend
    from runtime.contracts import ERROR_CODES
    from runtime.controller import NT8ControlPlane
    from runtime.server import NT8ApiServer

    results: list[Result] = []
    temp_nt8_dir = make_temp_nt8_dir()
    temp_workspace = Path(tempfile.mkdtemp(prefix="nt8_diag_workspace_"))

    server = None
    base_url = f"http://127.0.0.1:{PORT}"

    try:
        backends = {
            "file_write": FileWriteBackend(nt8_data_dir=temp_nt8_dir),
            "addon_http": AddonHttpBackend(port=18089),
            "dll_ati": DllAtiBackend(nt8_data_dir=temp_nt8_dir),
            "win32": Win32CaptureBackend(),
            "keyboard": KeyboardBackend(),
        }
        cp = NT8ControlPlane(nt8_data_dir=temp_nt8_dir, backends=backends, workspace=temp_workspace)
        server = NT8ApiServer(control_plane=cp, host="127.0.0.1", port=PORT)
        server.start_background()

        if not _wait_for_server(base_url, timeout_seconds=20.0):
            results.append(Result("FAIL", "server_boot", f"server did not answer {base_url}/v1/nt8/health within 20 seconds"))
            return report(results, "test_server_boot")
        results.append(Result("PASS", "server_boot", f"server answering at {base_url}"))

        # /v1/nt8/health
        status, data = _get(f"{base_url}/v1/nt8/health")
        if status == 200 and isinstance(data.get("payload"), dict):
            results.append(Result("PASS", "GET /v1/nt8/health", f"200, payload keys: {sorted(data['payload'].keys())}"))
        else:
            results.append(Result("FAIL", "GET /v1/nt8/health", f"status={status} body={data}"))

        # /v1/nt8/catalog
        status, data = _get(f"{base_url}/v1/nt8/catalog")
        payload = data.get("payload") if isinstance(data, dict) else None
        if status == 200 and isinstance(payload, dict) and len(payload) > 0:
            results.append(Result("PASS", "GET /v1/nt8/catalog", f"200, {len(payload)} commands"))
        else:
            results.append(Result("FAIL", "GET /v1/nt8/catalog", f"status={status} body={data}"))

        # /v1/nt8/capabilities (WS-A new endpoint, may not exist yet)
        status, data = _get_tolerant(f"{base_url}/v1/nt8/capabilities")
        if status == 404:
            results.append(Result("WARN", "GET /v1/nt8/capabilities", "404, not yet landed by WS-A"))
        elif status == 200:
            results.append(Result("PASS", "GET /v1/nt8/capabilities", f"200, body keys: {sorted(data.keys()) if isinstance(data, dict) else type(data)}"))
        else:
            results.append(Result("FAIL", "GET /v1/nt8/capabilities", f"unexpected status={status} body={data}"))

        # POST /v1/nt8/command terminal.detect, read only, must return a well
        # formed envelope regardless of whether the real NT8 process is running.
        status, data = _post(f"{base_url}/v1/nt8/command", {"command": "terminal.detect", "args": {}})
        if status != 200:
            results.append(Result("FAIL", "POST terminal.detect", f"expected HTTP 200, got {status}: {data}"))
        else:
            # Check the envelope shape actually produced by the live
            # NT8ApiServer._execute_envelope implementation: ok, error_code,
            # retryable, timing (dict with total_ms), result (dict with
          # success/driver/stdout/stderr/artifacts/metadata). Note: SKILL.md
            # documents an older envelope shape (command, backend, data, error,
            # timing_ms, cmd_id) that this server does not actually emit, see
            # the diagnostics report for that finding.
            required_keys = {"ok", "error_code", "retryable", "timing", "result"}
            present = required_keys.issubset(data.keys())
            timing_ok = isinstance(data.get("timing"), dict) and "total_ms" in data.get("timing", {})
            result_ok = isinstance(data.get("result"), dict) and "success" in data.get("result", {})
            if present and timing_ok and result_ok:
                results.append(
                    Result(
                        "PASS",
                        "POST terminal.detect",
                        f"well formed envelope, ok={data.get('ok')}, error_code={data.get('error_code')}, total_ms={data['timing']['total_ms']}",
                    )
                )
            else:
                results.append(Result("FAIL", "POST terminal.detect", f"envelope missing expected keys: {data}"))

        # POST an unknown command, must be a clean error envelope, not a 500 crash.
        status, data = _post(f"{base_url}/v1/nt8/command", {"command": "totally.bogus.command", "args": {}})
        expected_code = ERROR_CODES["unknown_command"]
        if status == 200 and data.get("ok") is False and data.get("error_code") == expected_code:
            results.append(Result("PASS", "POST unknown command", f"clean error envelope, error_code={expected_code}"))
        elif status >= 500:
            results.append(Result("FAIL", "POST unknown command", f"server crashed with HTTP {status} instead of a clean error envelope"))
        else:
            results.append(Result("FAIL", "POST unknown command", f"expected ok=false error_code={expected_code}, got status={status} body={data}"))

    finally:
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
        cleanup_temp_dir(temp_nt8_dir)
        cleanup_temp_dir(temp_workspace)

    return report(results, "test_server_boot")


if __name__ == "__main__":
    sys.exit(main())
