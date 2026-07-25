# Live API transcript

Captured 2026-07-25 on Windows 11 with NinjaTrader 8 installed but not running, so every response below is the real server answering with the target application closed. That is deliberate: it shows the honest degraded path, where the file and Win32 backends work and the in process AddOn bridge correctly reports itself unavailable.

The only edit made to these responses is the Windows username, replaced with `<you>`, and absolute repository paths shortened to `<repo>`. Nothing else was changed, reordered, or trimmed except where a block says it is truncated.

## Server start

```text
$ python -m runtime
NT8 data dir resolved to: C:\Users\<you>\Documents\NinjaTrader 8
NT8 API Server starting on http://127.0.0.1:8088
AddOn bridge expected at http://127.0.0.1:8089
Workspace: <repo>
Backends: file_write, addon_http, dll_ati, win32, keyboard
```

## GET /v1/nt8/health

```json
{"ok": true, "payload": {"nt8_running": false, "addon_connected": false, "dll_available": true, "backends": {"file_write": {"available": true}, "addon_http": {"available": false}, "dll_ati": {"available": true}, "win32": {"available": true}, "keyboard": {"available": true}}, "nt8_data_dir": "C:\\Users\\<you>\\Documents\\NinjaTrader 8", "workspace": "<repo>", "command_count": 64}}
```

## POST /v1/nt8/command, a working command

Request:

```json
{"command": "terminal.detect", "args": {}}
```

Response:

```json
{"ok": true, "request_id": null, "trace_id": null, "result": {"success": true, "driver": "win32", "stdout": "NinjaTrader not running (PIDs: [])", "stderr": "", "artifacts": [], "metadata": {"running": false, "pids": []}}, "verification": {"mode": "none", "performed": false, "api_passed": true, "visual_passed": null, "passed": true, "assertions": [], "contradiction": false, "evidence": {"run_id": "adhoc-20260725_201528_348181", "run_dir": "<repo>\\captures\\validation_runs\\adhoc\\terminal_detect\\20260725_201528_348181", "manifest_path": "<repo>\\captures\\validation_runs\\adhoc\\terminal_detect\\20260725_201528_348181\\001_terminal_detect_manifest.json", "response_path": "<repo>\\captures\\validation_runs\\adhoc\\terminal_detect\\20260725_201528_348181\\001_terminal_detect_response.json", "round": "adhoc", "feature": "terminal_detect", "timestamp": "20260725_201528_348181", "command_index": 1}}, "timing": {"attempts": 1, "execution_ms": 18.779, "verification_ms": 0.012, "total_ms": 48.933}, "error_code": "OK", "retryable": false, "idempotent_replay": false, "stage": null, "failure_signal": null, "fast_fail_triggered": false, "timeout_profile": "normal", "fast_fail_seconds": 3, "diagnostics": {}}
```

Note the evidence block: the manifest and the full response were also written to disk under `captures/validation_runs/` before the reply was returned.

## POST /v1/nt8/command, argument validation rejected before any side effect

Request:

```json
{"command": "chart.template_save", "args": {}}
```

Response, abbreviated to the fields that matter:

```json
{"ok": false, "result": {"success": false, "driver": "nt8", "stdout": "", "stderr": "missing required args for 'chart.template_save': ['name']", "metadata": {"failure_signal": "HARD_VALIDATION"}}, "timing": {"attempts": 1, "execution_ms": 0.053, "verification_ms": 0.008, "total_ms": 30.177}, "error_code": "ERR_VALIDATION", "retryable": false, "failure_signal": "HARD_VALIDATION", "fast_fail_triggered": true, "timeout_profile": "normal", "fast_fail_seconds": 4}
```

`execution_ms` is 0.053, so the command never reached a backend. Fast fail fired and the failure was classed as hard validation, which the caller can use to decide not to retry.

## POST /v1/nt8/command, backend genuinely unavailable

Same command with valid arguments, but the in process AddOn bridge is not listening because NinjaTrader is closed:

```json
{"ok": false, "result": {"success": false, "driver": "nt8", "stdout": "", "stderr": "backend 'addon_http' is not available", "metadata": {"failure_signal": "SOFT_BACKEND_UNAVAILABLE"}}, "timing": {"attempts": 1, "execution_ms": 6034.206, "verification_ms": 0.013, "total_ms": 6059.366}, "error_code": "ERR_INTERNAL", "retryable": false, "failure_signal": "SOFT_BACKEND_UNAVAILABLE"}
```

The failure signal separates "you called it wrong" from "the environment is not ready", which are different problems for an autonomous caller. Note also that `error_code` here is the generic `ERR_INTERNAL` rather than a dedicated bridge unavailable code, which is a rough edge worth tightening.

## GET /v1/nt8/capabilities

Truncated to four representative commands out of 64. The full payload publishes one entry per command.

```json
{"ok": true, "payload": {"generated_at_utc": "2026-07-25T20:15:26.226797+00:00", "commands": {
  "code.write_strategy": {"status": "working", "backends": ["file_write"], "description": "Write strategy .cs file to NinjaScript Strategies folder."},
  "compile.all": {"status": "best_effort", "backends": ["keyboard"], "description": "Compile all NinjaScript code (F5 hotkey)."},
  "chart.screenshot": {"status": "working", "backends": ["addon_http", "win32"], "description": "Capture screenshot of chart area."},
  "strategy.attach": {"status": "platform_gap", "backends": ["addon_http"], "description": "Attach a strategy to a chart for live or sim execution.", "remediation": "NT8 has no supported programmatic API for this action, confirmed by NinjaTrader staff. Use the NT8 GUI directly. For strategy.attach: set IsEnabled=true in State.SetDefaults so the strategy auto enables when its workspace loads."}
}}}
```

## GET /v1/nt8/catalog

Truncated to the first two entries. The catalog is the machine readable argument contract, which is what lets a caller validate a command before sending it.

```json
{"ok": true, "payload": {
  "code.write_strategy": {"description": "Write strategy .cs file to NinjaScript Strategies folder.", "required_args": ["name", "content"], "optional_args": [], "backends": ["file_write"]},
  "code.read": {"description": "Read a NinjaScript .cs file by name and type (strategy/indicator/addon).", "required_args": ["name", "type"], "optional_args": [], "backends": ["file_write"]}
}}
```

## Offline suites

Neither suite needs NinjaTrader. Both run against the real code, not mocks of it: the consistency suite reads the live command catalog and asserts the backends actually implement every action it routes to, and the parser suite feeds real Strategy Analyzer XML and real compiler output fixtures through the production parsers.

```text
$ python diagnostics/run_all.py
======================================================================
Running test_server_boot.py ...
======================================================================
[PASS] GET /v1/nt8/catalog: 200, 64 commands
[PASS] GET /v1/nt8/capabilities: 200, body keys: ['ok', 'payload']
[PASS] POST terminal.detect: well formed envelope, ok=True, error_code=OK, total_ms=33.627
[PASS] POST unknown command: clean error envelope, error_code=ERR_UNKNOWN_COMMAND
=== test_server_boot summary: 6 passed, 0 warned, 0 failed ===

======================================================================
Running test_parsers.py ...
======================================================================
[PASS] analyzer_status: action 'analyzer_status' succeeded and echoed fixture markers ['TestStrategy']
[PASS] analyzer_results: action 'analyzer_results' succeeded and echoed fixture markers ['1234.56', 'TotalNetProfit']
[PASS] analyzer_list_results: action 'analyzer_list_results' succeeded and echoed fixture markers ['TestStrategy_20260711_01']
[PASS] compile_status: action 'compile_status' succeeded and echoed fixture markers ['Unable to compile custom assembly']
[PASS] parse_compile_errors: action 'parse_compile_errors' succeeded and echoed fixture markers ['TestStrategy.cs', 'CS1002']
=== test_parsers summary: 5 passed, 0 warned, 0 failed ===

======================================================================
run_all summary
======================================================================
  test_consistency.py: exit 0 (OK)
  test_server_boot.py: exit 0 (OK)
  test_parsers.py: exit 0 (OK)
Totals: 279 passed, 0 warned, 0 failed
RESULT: PASS
```

```text
$ python runtime/selftest_ws_a.py
[PASS] GET /v1/nt8/catalog: status=200
[PASS] GET /v1/nt8/capabilities: status=200
[PASS] server shutdown
SUMMARY: 17 pass, 0 warn, 0 fail
RESULT: PASS

$ python runtime/selftest_ws_b.py
PASS: BridgeVersion constant is 2.0.0
=== SUMMARY ===
passed: 45
failed: 0
ALL CHECKS PASSED

$ python runtime/selftest_ws_c.py
[PASS] _sample_blank_ratio solid image -> ratio 1.0 :: 1.0
[PASS] _sample_blank_ratio varied image -> ratio < 1.0 :: 0.0625
[PASS] _sample_blank_ratio zero-size image -> ratio 0.0
==== SELFTEST SUMMARY: 81 passed, 0 failed, 81 total ====
```

## What this transcript does not prove

It does not show a compile, a backtest, or a chart screenshot, because NinjaTrader was closed when it was captured and launching it would have disturbed the machine it was captured on. Those paths were verified in an earlier session against NinjaTrader 8.1.7.2 and the results are summarised honestly in the README section "What is proven and what is not". Treat this transcript as proof that the API surface, the envelope, the validation, the capability map, and the parsers are real and running, not as proof of the GUI paths.
