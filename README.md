# NinjaTrader Control Plane

One HTTP API that lets a program (or an AI agent) develop trading strategies inside NinjaTrader 8, a Windows desktop platform that ships no automation API at all: write NinjaScript C#, compile it, read the compiler errors, run a backtest, and take screenshots, all over `POST /v1/nt8/command`.

## Live proof

This project drives a desktop application on Windows, so there is no URL to visit. Nothing here is deployable and I am not going to pretend otherwise. What there is instead is a transcript of the real server answering real requests on this machine, plus two offline suites anyone can run in under a minute.

Full verbatim transcript, captured 2026-07-25: [docs/evidence/api-transcript.md](docs/evidence/api-transcript.md). A short extract:

```
$ python -m runtime
NT8 data dir resolved to: C:\Users\<you>\Documents\NinjaTrader 8
NT8 API Server starting on http://127.0.0.1:8088
Backends: file_write, addon_http, dll_ati, win32, keyboard

$ curl -s http://127.0.0.1:8088/v1/nt8/health
{"ok": true, "payload": {"nt8_running": false, "addon_connected": false, "dll_available": true,
 "backends": {"file_write": {"available": true}, "addon_http": {"available": false},
 "dll_ati": {"available": true}, "win32": {"available": true}, "keyboard": {"available": true}},
 "command_count": 64}}

$ curl -s -X POST http://127.0.0.1:8088/v1/nt8/command \
    -H "Content-Type: application/json" -d '{"command":"terminal.detect","args":{}}'
{"ok": true, "result": {"success": true, "driver": "win32",
 "stdout": "NinjaTrader not running (PIDs: [])", "metadata": {"running": false, "pids": []}},
 "timing": {"attempts": 1, "execution_ms": 18.779, "total_ms": 48.933},
 "error_code": "OK", "retryable": false, "fast_fail_triggered": false}

$ python diagnostics/run_all.py
  test_consistency.py: exit 0 (OK)
  test_server_boot.py: exit 0 (OK)
  test_parsers.py: exit 0 (OK)
Totals: 279 passed, 0 warned, 0 failed
RESULT: PASS

$ python runtime/selftest_ws_a.py   # 17 pass
$ python runtime/selftest_ws_b.py   # 45 pass
$ python runtime/selftest_ws_c.py   # 81 pass
```

Related live work, a different project: [quantlab.alorny.cloud](https://quantlab.alorny.cloud), a deployed quant research dashboard.

## Why this is technically interesting

NinjaTrader 8 has no command line compiler, no scripting API, and no backtest API. NinjaTrader staff have confirmed this in their own support forum (ticket references are in [research/NT8_AUTOMATION_RESEARCH.md](research/NT8_AUTOMATION_RESEARCH.md)). The only way to compile a NinjaScript file is to press F5 inside an already open editor window. So the interesting problem is not "call the API", it is: how do you build something deterministic and observable on top of a GUI that was never meant to be driven?

Three parts of the answer are worth reading the code for.

**Compiling by keystroke, verified by artifact.** A naive `SendInput` F5 gets silently dropped by NinjaTrader's WPF hotkey binding. The working recipe is to disable the Windows foreground lock timeout so a background server can legitimately take focus, then send F5 as a real `keybd_event` key down and key up held roughly 80 milliseconds apart. Success is never inferred from the keystroke; it is proven by `NinjaTrader.Custom.dll` changing mtime, typically 3 to 4 seconds later. On failure NinjaTrader restores the old DLL, often writes no trace line and shows no dialog, so "no new assembly inside the timeout" is itself the failure signal (`ERR_COMPILE_NO_NEW_ASSEMBLY`), and the control plane screenshots the editor Errors panel because that panel is the only place the file, line, and CS error code exist.

**Honest capability tiers instead of fake success.** Every one of the 64 commands is tagged `working`, `best_effort`, or `platform_gap`. A `platform_gap` command does not silently no-op: it returns an error code plus a remediation string telling the caller what to do by hand instead. `GET /v1/nt8/capabilities` publishes the whole map, so a caller can plan around the gaps before it starts. Attaching a strategy to a chart is a real permanent gap, and the API says so.

**Every command leaves an evidence trail.** Each call writes a manifest and its full response JSON into `captures/validation_runs/`, and screenshot backed commands attach the image. The response envelope carries the error code, the failure signal class (hard validation versus soft backend unavailable), retryability, attempt count, and separate execution and verification timings. That is what makes an autonomous write, compile, read errors, fix, recompile loop debuggable after the fact rather than a black box.

## Architecture

- `runtime/server.py`: stdlib HTTP server. Shapes every response into one envelope, maps exceptions onto a fixed error taxonomy, and sanitizes results so nothing unserializable escapes.
- `runtime/controller.py`: the command catalog (64 commands), argument validation, the command to backend routing table, the capability tiers, and the macros (`compile_and_test`, `iterate_strategy`, `full_dev_cycle`) that chain the primitives into one call.
- `runtime/backends/file_write.py`: the only fully deterministic backend. NinjaScript file IO, compile status from DLL mtime, compile error parsing, and Strategy Analyzer XML result parsing.
- `runtime/backends/keyboard.py`: the GUI driver. Compile, chart open and close, Strategy Analyzer sequences, autotrading toggle. All the focus and modal dialog handling lives here.
- `runtime/backends/addon_http.py` plus `runtime/assets/nt8/AntigravityBridgeAddOn.cs`: a C# AddOn that runs an `HttpListener` on port 8089 inside the NinjaTrader process, because only in process NinjaScript code can reach chart, account, and market data objects. Python talks to it over plain HTTP.
- `runtime/backends/dll_ati.py`: the file based Automated Trading Interface. Writes OIF command files into NinjaTrader's `incoming/` folder and reads status back from `outgoing/`, used for simulation orders and positions.
- `runtime/backends/win32_capture.py`: process detection, window focus and placement, and `PrintWindow` screenshots with blank frame detection, since a background capture of a SharpDX rendered chart can come back empty.
- `runtime/evidence.py`, `runtime/idempotency.py`, `runtime/lifecycle.py`, `runtime/visual.py`: the cross cutting machinery, respectively the capture trail, replay protection for repeated commands, server lifecycle, and screenshot based verification.

## How to run it

Requires Windows, Python 3.11 or newer, and a NinjaTrader 8 install. Only the standard library is needed; Pillow is optional and only used for screenshot processing.

```powershell
git clone https://github.com/Hieronymos2077/ninjatrader-control-plane.git
cd ninjatrader-control-plane

# offline suites, no NinjaTrader needed
python diagnostics/run_all.py
python runtime/selftest_ws_a.py

# start the control plane on 8088
python -m runtime

# or via the launcher, which polls its own health endpoint
powershell -ExecutionPolicy Bypass -File bin\start_nt8_api_server.ps1
```

Then drive it:

```powershell
curl -s -X POST http://localhost:8088/v1/nt8/command `
  -H "Content-Type: application/json" `
  -d '{"command":"code.write_strategy","args":{"name":"ExampleBreakoutStrategy","content":"..."}}'
```

`bin\nt8_command_api.ps1` wraps the same call, and `bin\deploy_addon.ps1` installs the C# bridge. [docs/OPERATIONS_QUICKSTART.md](docs/OPERATIONS_QUICKSTART.md) is the bootstrap runbook and [docs/RECIPES.md](docs/RECIPES.md) has copy paste sequences for the full development loop.

## What is proven and what is not

Honest status, because a control plane that lies about its own coverage is worse than no control plane.

Proven live against a real NinjaTrader 8.1.7.2 install: `terminal.detect`, `terminal.launch`, `terminal.capture`, `code.write_strategy`, `code.list`, `code.delete`, `code.search`, `compile.all` in both directions (a passing compile with the DLL mtime advancing in about 3.4 seconds, and a deliberately broken file returning `ERR_COMPILE_NO_NEW_ASSEMBLY` with a screenshot of the CS errors), `logs.trace`, `system.capabilities`.

Implemented and unit covered but not yet exercised end to end live: Strategy Analyzer result parsing (validated against a real Strategy Analyzer XML export and fixtures), the ATI order line format, and the C# bridge, which compiles clean but does not start its listener until NinjaTrader is restarted once after the first deploy.

Known partial: `tester.open` drives the Control Center New menu and verifies the resulting window, but opening a WPF menu with a synthetic click from a background process is not reliable. When it fails it returns `ANALYZER_NOT_OPEN` with coordinate overrides rather than pretending. The workaround is to open the Strategy Analyzer once by hand, after which it persists in the workspace and `tester.configure`, `tester.start`, and `tester.results` operate on it.

Permanent platform gaps, confirmed by NinjaTrader staff and not bugs here: attaching or detaching a strategy on a chart, and saving or applying chart templates.

## Deliberately out of scope

- Live money trading. Order placement targets simulation accounts through the ATI file interface. There is no broker credential handling anywhere in this repo.
- Cross platform support. This automates a Windows desktop application through Win32 and WPF; there is nothing portable about it.
- Strategy quality. This is the harness that writes and compiles and measures. It has no opinion about whether a strategy is any good.
- Authentication. The server binds loopback and assumes a trusted local caller. Exposing it on a network would need auth added first.

## Design documents

The interesting reading is not only the code.

- [CONTRACT.md](CONTRACT.md): the design contract. Empirically verified platform facts, the command map, and the compile and backtest flows.
- [docs/SKILL_CONTRACT.md](docs/SKILL_CONTRACT.md): the request and response envelope schema, the full error taxonomy, backend priority, and the idempotency and evidence rules.
- [docs/GOTCHAS.md](docs/GOTCHAS.md): the platform knowledge that cost the most to find. Read this one first if you only read one.
- [research/AUDIT_REPORT.md](research/AUDIT_REPORT.md) then [research/AUDIT_BASELINE_STATUS.md](research/AUDIT_BASELINE_STATUS.md): an adversarial audit of an earlier build of this code that found concrete bugs with file and line citations (wrong hotkeys, argument name mismatches between the catalog and the backends, invalid NinjaTrader API calls in the C# AddOn), followed by the review that tracks which of them were actually fixed. They are in the repo on purpose. Reading a project's own critical audit tells you more than reading its feature list.
- [research/PLATFORM_API_OPTIONS.md](research/PLATFORM_API_OPTIONS.md): why the backend mix is what it is, compared against the other six ways to automate this platform.
- [SKILL.md](SKILL.md): the agent facing interface. This control plane was built to be driven by an AI coding agent, and this file is the contract that agent reads.
