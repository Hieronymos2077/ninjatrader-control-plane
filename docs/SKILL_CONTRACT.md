# Skill Contract: nt8-api-control

## Purpose
Provide an API first control plane for NinjaTrader 8, focused on the NinjaScript development workflow, write, compile, backtest, iterate, plus chart operations, state inspection, and demo account trading.

## Triggers
- Write/edit NinjaScript strategies, indicators, or AddOns
- Compile NinjaScript code
- Open/manage charts
- Add/remove indicators on a chart, or check what is applied
- Run backtests in the Strategy Analyzer
- Get terminal, account, or strategy state
- Capture screenshots
- Place/cancel/modify orders (sim accounts only)

## Backend Strategy

| Priority | Backend | Use For |
|---|---|---|
| 1 | `file_write` | Code and template file I/O (write/read/list/delete/search), compile status/error parsing, Strategy Analyzer xml result parsing |
| 2 | `keyboard` | Compilation (F5) and GUI only operations (chart open/close/switch, Strategy Analyzer configure/start, autotrading toggle) |
| 3 | `addon_http` | Chart/indicator/strategy queries, screenshots, account state, market data, log output |
| 4 | `dll_ati` | Trading operations (place/cancel/close/reverse orders, position/order queries) via file based OIF, not a raw TCP dial |
| 5 | `win32` | Process detection/launch/kill, window focus/arrange, background safe window screenshots |

Backend is auto selected by the command router (`NT8ControlPlane._resolve_backend` in `runtime\controller.py`) based on the command's declared `backends` list in the catalog, preferring the first available backend that also has an entry in the action map. Explicit override is supported via the `backend` field in the request envelope (`"backend": "keyboard"`, etc), or `-Backend` on the CLI.

## Live Trading Safety

- Default: sim/demo accounts only (`Sim101` and similar).
- Never enable autotrading (`strategy.enable_autotrading`) or place a real order without the user explicitly asking for it in that exact turn.
- `strategy.enable_autotrading` (Ctrl+E) toggles the whole platform's autotrading state, it has no per strategy targeting, treat it as a global switch.
- Trade commands (`trade.*`) write OIF files to `incoming\` regardless of account; NT8 only acts on them if ATI is enabled in Control Center options, so a silently ignored trade is possible if ATI is off, this is not itself a rejected trade guard, just a platform prerequisite.

## Error Code Taxonomy

Real codes from `runtime\contracts.py`'s `ERROR_CODES`, mapped from `stderr` text by `NT8ApiServer._map_error_code` in `runtime\server.py`.

| Error Code | Meaning | Retryable |
|---|---|---|
| `OK` | Success | n/a |
| `ERR_VALIDATION` | Missing/bad required args | No |
| `ERR_UNKNOWN_COMMAND` | Command not in the catalog | No |
| `ERR_BACKEND_UNSUPPORTED` | Requested backend cannot handle this command | No |
| `ERR_TIMEOUT` | Command timed out | Yes |
| `ERR_ADDON_TIMEOUT` | AddOn HTTP request timed out, or the AddOn is unreachable/heartbeat stale | Yes |
| `ERR_NT8_UNAVAILABLE` | NT8 process not running | No |
| `ERR_COMPILE_FAILED` | NinjaScript compile failed, `errors[]` in the compile metadata has detail | No, fix the code first |
| `ERR_COMPILE_TIMEOUT` | Compile did not finish (no DLL mtime change, no failure marker) within the timeout | Sometimes, if NT8 was just slow |
| `ERR_EDITOR_NOT_OPEN` | No NinjaScript Editor window found and none could be opened from the Control Center | No, open it manually first |
| `ERR_ANALYZER_NOT_OPEN` | No Strategy Analyzer window found (for `tester.configure`/`tester.start`), or a backtest never completed within the poll timeout (for `macro.compile_and_test`) | No, call `tester.open` (or check the window) first |
| `ERR_SYMBOL_NOT_FOUND` | Instrument not found in NT8 | No |
| `ERR_TRADE_GUARD` | Live account rejected without explicit confirmation | No |
| `ERR_TRADE_REJECTED` | Order rejected by NT8/broker | No |
| `ERR_NOT_SUPPORTED_BY_PLATFORM` | Confirmed NT8 platform gap (`strategy.attach`, `strategy.detach`, `chart.template_save`, `chart.template_apply`), there is no API, use the GUI | No, never retry, use the documented workaround |
| `ERR_ADDON_STALE` | The compiled bridge AddOn's `/version` does not match its current source, redeploy was not followed by a recompile | No, run `compile.all` again |
| `ERR_VERIFICATION_FAILED` | The command's API result said success but visual verification (`verify_mode: visual`/`api+visual`) contradicted it | Yes |
| `ERR_INTERNAL` | Unexpected server error | Yes |

`retryable` in the response envelope is also forced to `false` whenever a "hard" failure signal is detected (validation errors, unknown command, backend unsupported, compile failed, trade guard/rejection, verification failure, platform gap), regardless of the error code's normal retryability, so the server never blindly retries something that cannot succeed by retrying.

## Request Envelope Fields (accepted by `POST /v1/nt8/command`)

| Field | Type | Default | Notes |
|---|---|---|---|
| `command` | string | required | Must exist in `NT8_COMMAND_CATALOG` |
| `args` | object | `{}` | Command specific args |
| `backend` | string | `"auto"` | `auto`, `keyboard`, `file_write`, `addon_http`, `dll_ati`, `win32` |
| `timeout_seconds` | int | derived from command class and `timeout_profile` | See `_COMMAND_TIMEOUT_BASE_SECONDS` in `server.py` |
| `timeout_profile` | string | `"normal"` | `fast` (0.6x), `normal` (1x), `slow` (1.5x) |
| `fast_fail_seconds` | int | derived | How fast a hard-failure attempt gives up before the normal timeout |
| `request_id` | string or null | `null` | Idempotency key, see below |
| `trace_id` | string or null | `null` | Opaque correlation id, echoed back, not interpreted |
| `instance_id` | string or null | `null` | Opaque correlation id, echoed back, not interpreted |
| `response_mode` | string | `"normal"` | `compact` (success/driver/artifacts/metadata only), `normal`, `diagnostic` (adds stdout/stderr length counters) |
| `verify_mode` | string | `"none"` | `none`, `api` (envelope's own success flag only), `visual`, `api+visual` |
| `risk_context` | object or null | `null` | Reserved, passed through, not currently interpreted by any command |
| `return_fields` | list of strings or null | `null` | If set, `result.metadata` is filtered down to only these keys |
| `max_retries` | int | `0` | Clamped to 0 to 5, only retryable (non hard) failures are retried, with `0.15 * (attempt+1)` second backoff |

## Response Envelope (real shape, from `server.py`'s `_execute_envelope`)

```json
{
  "ok": true,
  "request_id": null,
  "trace_id": null,
  "result": {"success": true, "driver": "nt8", "stdout": "...", "stderr": "", "artifacts": ["..."], "metadata": {}},
  "verification": {"mode": "none", "performed": false, "api_passed": true, "visual_passed": null, "passed": true, "assertions": [], "contradiction": false, "evidence": {}},
  "timing": {"attempts": 1, "execution_ms": 0.0, "verification_ms": 0.0, "total_ms": 0.0},
  "error_code": "OK",
  "retryable": false,
  "idempotent_replay": false,
  "stage": null,
  "failure_signal": null,
  "fast_fail_triggered": false,
  "timeout_profile": "normal",
  "fast_fail_seconds": 4,
  "diagnostics": {}
}
```

`result` is always `{success, driver, stdout, stderr, artifacts, metadata}`, this is the backend's raw `ExecutionResult` serialized, never a different shape per command. Command specific data lives entirely inside `result.metadata`.

## Idempotency

- Every request can include a `request_id`.
- If a `request_id` has been seen before (within the TTL), the stored full response is replayed verbatim with `idempotent_replay: true` set, the command is never re-executed.
- Backing store: SQLite at `.nt8skill\state\idempotency.db` under the project root.
- TTL: 24 hours by default.

## Evidence Trail

- Every command execution through `POST /v1/nt8/command` is recorded, controlled by the `NT8_EVIDENCE` env var (`on` by default).
- Stored as JSON under `captures\validation_runs\<round>\<feature>\<timestamp>\<NNN>_<feature>_manifest.json` and a matching `_response.json`, where `round`/`feature`/`timestamp`/`command_index` come from an optional `evidence` object in the request, or sane defaults (`round: "adhoc"`, `feature` derived from the command name, `timestamp` a UTC token) if omitted.
- Retrieve via `GET /v1/nt8/evidence?run_id=<id>&limit=100`.
- Includes: command, args, backend, timing, the full result payload, verification status, and notes (`response_mode`, `verify_mode`, `timeout_profile`, `fast_fail_seconds`).

## Lifecycle and Metrics

- Every command transitions through a state machine (`queued` to `sent` to `verified` to `done`/`failed`) recorded in SQLite at `.nt8skill\state\lifecycle.db`.
- `GET /v1/nt8/metrics?since_seconds=3600` returns aggregate success/failure counts for the recent window.
- `GET /v1/nt8/errors?limit=50` returns recent dead lettered failures (command, stderr, verification, reason).
