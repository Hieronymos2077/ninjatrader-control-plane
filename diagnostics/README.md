# Diagnostics

Dynamic test suite for this control plane. Every check reads the live code in
runtime\ at run time, nothing here is a hardcoded copy of an expected command
or action list. That matters because WS-A, WS-B, and WS-C edit runtime\ in
parallel, so a hardcoded expectation would go stale within hours.

## Run everything

```
.venv\Scripts\python.exe diagnostics\run_all.py
```

Exit code 0 means no FAIL anywhere. WARN lines are fine, they mark work another
workstream has not landed yet (for example the new file_write actions from
CONTRACT.md, or the system.capabilities endpoint).

## What each suite guards

### test_consistency.py

Loads NT8_COMMAND_CATALOG, _BACKEND_ACTION_MAP, and
NT8ControlPlane._macro_dispatch from the real runtime.controller module, and
the real dispatch tables of every backend in runtime\backends\ (read via
static AST parsing, so nothing is actually invoked, no keystrokes, no network
calls, no file writes). Checks:

- (a) every catalog command either lists a backend that has an entry in
  _BACKEND_ACTION_MAP, or is a controller level command (macro.*, system.*,
  bridge.deploy, or backends == ["auto"]).
- (b) every action name in _BACKEND_ACTION_MAP actually exists in the target
  backend's real dispatch table.
- (c) every backend name used in _BACKEND_ACTION_MAP is registered in the
  backends dict inside runtime\__main__.py's main().
- (d) required_args and optional_args in the catalog are lists of strings.
- (e) every macro.* command in the catalog has a handler in
  NT8ControlPlane._macro_dispatch.

This is the class of test that would have caught CRIT-3 (addon_http actions
wired in the map but never implemented) and CRIT-5 (tester.configure mapped
but stubbed) from the baseline audit, at the structural level.

### test_server_boot.py

Boots the real NT8ApiServer, the real NT8ControlPlane, and the real backend
classes, wired to a TEMP workspace and a TEMP directory shaped like
Documents\NinjaTrader 8 (bin\Custom, log, trace, strategyanalyzerlogs,
incoming, outgoing). Listens on port 18090, never touches the real NT8 data
dir. Requests:

- GET /v1/nt8/health, GET /v1/nt8/catalog: must both return 200 with a
  populated payload.
- GET /v1/nt8/capabilities: WARN on 404 (not yet landed by WS-A), PASS on 200.
- POST /v1/nt8/command with terminal.detect: must return a well formed
  envelope (ok, error_code, retryable, timing.total_ms, result.success)
  whether or not the real NinjaTrader process happens to be running. This
  action only reads the Windows process list, it never launches or kills
  anything.
- POST /v1/nt8/command with an unknown command name: must return a clean
  ok=false envelope with error_code ERR_UNKNOWN_COMMAND, never an HTTP 500.

Known finding, not a test bug: SKILL.md documents an envelope shape with top
level keys command, backend, data, error, timing_ms, and cmd_id. The real
server in runtime\server.py returns a different shape (request_id, trace_id,
result, timing.total_ms, no cmd_id at all). This suite asserts against the
real shape the server actually returns, and the mismatch is called out in the
workstream report instead of being hidden behind a permanently failing test.

### test_parsers.py

Builds two TEMP fixtures matching the empirical facts in CONTRACT.md:

- A strategyanalyzerlogs XML pair (`TestStrategy_20260711_01.xml/.cs`) with
  the StrategyAnalyzerLog/StrategyAnalyzerGridEntry schema and pipe delimited
  SummaryPerformancesSerialize entries (TotalNetProfit=1234.56 among others).
- A trace file containing the deterministic failure marker line `Unable to
  compile custom assembly. Original version has been restored.` plus a
  representative compile error line.

For each of the five new file_write actions from CONTRACT.md (compile_status,
parse_compile_errors, analyzer_status, analyzer_results,
analyzer_list_results), this suite calls FileWriteBackend.execute directly
(no network, no keyboard, no process control, TEMP paths only). If the action
is not yet implemented, FileWriteBackend returns a clean "Unknown action"
failure and this suite reports WARN. Once implemented, the suite asserts the
response text contains the fixture's known numbers or markers (for example
"1234.56" and "TotalNetProfit" for analyzer_results), which is as close to
"parsed stats match the fixture exactly" as is possible without a published
output schema for these not yet landed actions.

## Adding a new check

Keep deriving everything from the live catalog, action map, and dispatch
tables. Never hardcode a list of command names that should exist, only assert
properties that must hold about whatever is currently there.
