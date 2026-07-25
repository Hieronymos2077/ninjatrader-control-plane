---
name: nt8-api-control
description: Use this skill when the user asks to control NinjaTrader 8 (NT8). It provides a robust, API-first control plane for writing NinjaScript code, compiling, chart operations, indicator/strategy lifecycle, backtesting, state inspection, and the autonomous write to compile to backtest development loop.
---

# NT8 API Control Skill

Use this skill for deterministic, API-first NinjaTrader 8 control. Primary use case: an AI driven NinjaScript development workflow, write code, compile it, backtest it, iterate, all through one command surface instead of manual clicking.

Project root: `C:\path\to\ninjatrader-control-plane`. Every path in this skill is relative to that root unless stated otherwise.

**Verified live, 2026-07-12, against a real NinjaTrader 8.1.7.2 install.** Confirmed working end to end: `terminal.detect`, `terminal.launch` (started NT8), `terminal.capture` (real PNG with blank detection), `code.write_strategy`, `code.list` (listed the user's real strategies), `code.delete`, `compile.all` (both a passing compile with a DLL mtime change in about 3.4 seconds, and a failing compile that returned `ERR_COMPILE_NO_NEW_ASSEMBLY` with a screenshot), `logs.trace`, `system.capabilities`. The compile mechanism internals, the new AddOn authorization dialog, and the bridge restart requirement below were all discovered and confirmed in that session.

## Core Rule Set

1. API first: use the NT8 command API below before any manual click path.
2. Truthful success: a command is success only when `ok` is true in the response envelope. Compile success is proven by the DLL mtime changing, never by absence of an error. Backtest completion is proven by a new file appearing in `strategyanalyzerlogs`, never by a fixed sleep.
3. Honest failure on platform gaps: some commands (`strategy.attach`, `strategy.detach`, `chart.template_save`, `chart.template_apply`) have no supported NT8 API at all. They always return `ok: false` with `error_code: ERR_NOT_SUPPORTED_BY_PLATFORM`. Never treat that as a bug to route around silently, report the remediation to the user.
4. Backup before overwrite: `code.write_strategy` / `code.write_indicator` / `code.write_addon` / `code.delete` write a `.bak` copy of any existing file before touching it.
5. Never touch a NinjaScript file this session did not create. The user has real strategies in `bin\Custom\Strategies\` (several unrelated production strategies). Reading them is fine, editing or deleting them is not, unless the user explicitly asks.
6. Sim account only. Never enable autotrading or place a live order without the user explicitly asking for it in that exact turn.

## Tools

### PowerShell CLI

```powershell
& "C:\path\to\ninjatrader-control-plane\bin\nt8_command_api.ps1" -Command <command> -ArgsJson '<json>' -TimeoutSec <n>
```

Other parameters: `-Backend auto|keyboard|file_write|addon_http|dll_ati|win32`, `-ResponseMode normal|compact|diagnostic`, `-RequestId <id>` (idempotency key), `-Port <n>` (defaults to `$env:NT8_API_PORT` or 8088).

### HTTP API

```
POST http://localhost:8088/v1/nt8/command
Content-Type: application/json

{"command": "code.write_strategy", "args": {"name": "MyStrategy", "content": "..."}}
```

Other endpoints: `GET /v1/nt8/health`, `GET /v1/nt8/catalog`, `GET /v1/nt8/capabilities`, `GET /v1/nt8/shortcuts`, `GET /v1/nt8/metrics`, `GET /v1/nt8/errors`, `GET /v1/nt8/evidence?run_id=<id>&limit=100`, `POST /v1/nt8/command/batch` (body `{"commands": [...], "stop_on_error": false}`).

### Starting the server

```powershell
powershell -ExecutionPolicy Bypass -File "C:\path\to\ninjatrader-control-plane\bin\start_nt8_api_server.ps1"
```

Flags: `-Hidden` (start without a foreground console window), `-Stop` (stop the server, refuses to kill anything that is not python.exe from this project's venv), `-Port <n>` (default 8088), `-AddonPort <n>` (default 8089, must match the NT8 AddOn's listener). The script runs `.venv\Scripts\python.exe -m runtime` from the project root, this is the only correct launch command, `python runtime\server.py` has no main block and exits instantly while looking like it started.

## Response Envelope (real shape, from server.py)

Every `/v1/nt8/command` response is this shape:

```json
{
  "ok": true,
  "request_id": null,
  "trace_id": null,
  "result": {
    "success": true,
    "driver": "nt8",
    "stdout": "Wrote 842 bytes to C:\\Users\\<you>\\Documents\\NinjaTrader 8\\bin\\Custom\\Strategies\\MyStrategy.cs",
    "stderr": "",
    "artifacts": ["C:\\Users\\<you>\\Documents\\NinjaTrader 8\\bin\\Custom\\Strategies\\MyStrategy.cs"],
    "metadata": {"path": "C:\\Users\\<you>\\Documents\\NinjaTrader 8\\bin\\Custom\\Strategies\\MyStrategy.cs", "size": 842}
  },
  "verification": {
    "mode": "none",
    "performed": false,
    "api_passed": true,
    "visual_passed": null,
    "passed": true,
    "assertions": [],
    "contradiction": false,
    "evidence": {"path": "captures/validation_runs/adhoc/code_write_strategy/20260712_120000_000000/001_code_write_strategy_response.json"}
  },
  "timing": {"attempts": 1, "execution_ms": 4.2, "verification_ms": 0.1, "total_ms": 5.7},
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

On failure `ok` is false, `result.success` is false, `error_code` is one of the codes in the taxonomy below, and `result.stderr` / `result.metadata` carry the reason. `verification` only does real work when the request sets `verify_mode` to `api`, `visual`, or `api+visual`, the default `none` just mirrors `result.success`.

## Command Reference (from the live catalog in `runtime\controller.py`)

Capability tiers come straight from `NT8ControlPlane.command_capabilities()`: `working` (deterministic, no known failure surface beyond bad args), `best_effort` (GUI/keyboard/reflection automation, can fail even when NT8 is healthy), `platform_gap` (NT8 has no supported API, always fails, this is not a bug). Call `system.capabilities` at runtime for the live version of this table plus current backend health.

### code.* (file_write, working)

| Command | Required args | Optional args | Notes |
|---|---|---|---|
| `code.write_strategy` | `name`, `content` | | Writes to `bin\Custom\Strategies\<name>.cs`, backs up existing file first |
| `code.write_indicator` | `name`, `content` | | Writes to `bin\Custom\Indicators\<name>.cs` |
| `code.write_addon` | `name`, `content` | | Writes to `bin\Custom\AddOns\<name>.cs` |
| `code.read` | `name`, `type` | | `type` is `strategy`, `indicator`, `addon`, or `drawingtool` |
| `code.list` | | `type` | Lists all `.cs` files, newest first |
| `code.delete` | `name`, `type` | | Backs up before deleting |
| `code.search` | `query` | | `query` is a regex (falls back to a literal match if invalid), searched across `.cs` files |

### compile.* (keyboard / file_write)

| Command | Required args | Backend | Tier | Notes |
|---|---|---|---|---|
| `compile.all` | | keyboard | best_effort | Held F5 in the NinjaScript Editor (a document tab must be open), deterministic completion via DLL mtime, auto handles the new AddOn authorization dialog if it appears, failure returns `ERR_COMPILE_NO_NEW_ASSEMBLY` plus a screenshot of the Errors panel |
| `compile.check` | | file_write | working | Reads current DLL mtime/size plus the last 30 compile related trace lines, does not trigger a compile |
| `compile.errors` | | file_write | best_effort | Parses `trace\*.txt` and `log\*.txt` for `file(line,col): error CODE: message` and `Unable to compile` markers, optional `since` ISO timestamp |

### chart.* (keyboard / addon_http)

| Command | Required args | Optional args | Backend | Tier |
|---|---|---|---|---|
| `chart.list` | | | addon_http | working |
| `chart.open` | `symbol` | `period` | keyboard | best_effort |
| `chart.close` | | `chart_id` | addon_http, keyboard | best_effort |
| `chart.switch_instrument` | `symbol` | `chart_id` | keyboard | best_effort |
| `chart.switch_timeframe` | `period` | `chart_id` | keyboard | best_effort |
| `chart.indicator_list` | | `chart_id` | addon_http | working |
| `chart.indicator_add` | `indicator` | `chart_id`, `params` | addon_http | best_effort (reflection, fragile across NT8 updates) |
| `chart.indicator_remove` | `indicator` | `chart_id` | addon_http | best_effort |
| `chart.screenshot` | | `chart_id`, `name` | addon_http, win32 | working |
| `chart.template_save` | `name` | `chart_id` | addon_http | **platform_gap** |
| `chart.template_apply` | `name` | `chart_id` | addon_http | **platform_gap** |

### strategy.* (addon_http / keyboard)

| Command | Required args | Optional args | Backend | Tier |
|---|---|---|---|---|
| `strategy.attach` | `strategy`, `symbol` | `period`, `params` | addon_http | **platform_gap** |
| `strategy.detach` | `strategy` | | addon_http | **platform_gap** |
| `strategy.list_running` | | | addon_http | working |
| `strategy.state` | `strategy` | | addon_http | working |
| `strategy.enable_autotrading` | | | keyboard | best_effort (Ctrl+E, no per strategy targeting, toggles the whole platform) |

### tester.* (Strategy Analyzer, keyboard / file_write)

| Command | Required args | Optional args | Backend | Tier |
|---|---|---|---|---|
| `tester.open` | | | keyboard | best_effort (Ctrl+R) |
| `tester.configure` | `strategy`, `symbol` | `period_type`, `period_value`, `from_date`, `to_date`, `account` | keyboard | best_effort, always returns `verified: false` by design. `args.steps` is also accepted at runtime to override the default navigation sequence, see below, it is not in the catalog's formal optional_args list |
| `tester.start` | | `key` (default `f5`) | keyboard | best_effort, always returns `verified: false` by design |
| `tester.status` | | `since`, `strategy` | file_write, win32 | best_effort |
| `tester.results` | | `strategy`, `since`, `name` | file_write, win32 | best_effort |
| `tester.list_results` | | `strategy`, `limit` (default 10) | file_write | best_effort |

### trade.*, account.*, position.*, order.*, market_data.*

Unchanged from the standard ATI/AddOn split. `trade.*` is `dll_ati` (OIF files in `incoming\`), `account.info`/`market_data.get` try `addon_http` first then `dll_ati`, `market_data.subscribe`/`account.list`/`position.list` are `addon_http`, `position.get`/`order.list`/`order.status` are `dll_ati`. All working tier except where noted. Full required/optional args are in `runtime\controller.py`'s `NT8_COMMAND_CATALOG`, they have not changed shape from prior versions of this skill.

### terminal.*, logs.*, bridge.*

`terminal.detect` is working; `terminal.launch`, `terminal.kill`, `terminal.focus`, `terminal.capture`, `terminal.arrange` are best_effort (win32). `logs.output` (addon_http/file_write), `logs.journal`, `logs.trace` (file_write) are working. `bridge.status` (addon_http) is working, `bridge.deploy` (writes the bridge AddOn source then compiles) is best_effort.

### system.capabilities (working, no backend)

No args. Returns the live version of the table above plus `backend_health` (same shape as `GET /v1/nt8/health`). Call this whenever unsure what will and will not work right now.

### macro.* (composite, all best_effort)

| Command | Required args | Optional args | What it does |
|---|---|---|---|
| `macro.develop_indicator` | `name`, `content`, `symbol` | `period` | write indicator, compile, open chart, add indicator, screenshot |
| `macro.develop_strategy` | `name`, `content`, `symbol` | `period` | write strategy, compile, open chart, screenshot. Never fakes the attach step, see below |
| `macro.compile_and_test` | `strategy`, `symbol` | `period_type`, `period_value`, `from_date`, `to_date`, `account`, `timeout_seconds` | compile, open/configure/start Strategy Analyzer, poll for a new analyzer xml since T0, parse results, screenshot |
| `macro.iterate_strategy` | `name`, `content`, `symbol` | same as `compile_and_test` | list the prior result for `name` first, write the new code, run `compile_and_test`, return `before`/`after` stats |
| `macro.chart_open_robust` | `symbol` | `period` | detect NT8, launch it if not running, retry `chart.open` up to 3 times, screenshot |
| `macro.full_dev_cycle` | `name`, `content`, `symbol` | same as `compile_and_test` | write strategy then run `compile_and_test` in one call. **This is the primary autonomous dev loop command.** |

`macro.develop_strategy` never calls `strategy.attach`. NT8 has no supported AddOn API to enable a strategy (confirmed by NinjaTrader staff, tickets SFT-977 and SFT-1445). The macro writes, compiles, opens the chart, screenshots, and returns `attach_required_manual: true` with a `attach_note` telling you to either attach it from the chart GUI (right click the chart, Strategies, add it) or set `IsEnabled = true` in the strategy's `State.SetDefaults` so it auto enables when its workspace next loads. Never report a strategy as "running" unless `strategy.list_running` or `strategy.state` confirms it.

### Platform gaps (always `NOT_SUPPORTED_BY_PLATFORM`, do not try to route around them)

`strategy.attach`, `strategy.detach`, `chart.template_save`, `chart.template_apply`. NinjaTrader staff have confirmed there is no supported programmatic API for these (forum threads cited in `research\NT8_AUTOMATION_RESEARCH_2026-07.md`, tickets SFT-977 and SFT-1445). Workarounds:
- Strategy attach/detach: do it from the chart GUI (right click chart, Strategies), or set `IsEnabled = true` in `State.SetDefaults` so the strategy auto enables the next time its workspace loads.
- Chart templates: save/apply templates from the chart GUI (right click chart, Templates).

## The Compile Flow (deterministic)

`compile.all` (backend `keyboard`, action `compile`) does the following, this is the ONLY reliable way to compile NinjaScript, there is no CLI compiler:

1. Record `NinjaTrader.Custom.dll` mtime and size, and the current trace file's byte offset.
2. Find a window titled "NinjaScript Editor". If none exists, find "Control Center" instead, focus it, send Ctrl+N to open a new NinjaScript Editor, wait 2 seconds, look again.
3. If still no editor window: fail fast with `error_code EDITOR_NOT_OPEN` and a remediation string. **Fix**: in NinjaTrader, open the Control Center menu, choose New, then NinjaScript Editor, then retry.
4. Focus the editor window, send F5.
5. Poll up to `timeout_seconds` (default 120s): if the DLL mtime changes, that is success. If a trace line contains "unable to compile" (case insensitive), that is failure, collect matching lines as `errors`.
6. Return `{success, duration_ms, dll_mtime_before, dll_mtime_after, trace_lines, errors}`. `success` is only ever true when the mtime actually changed, never inferred from silence.

If the compile fails, NT8 restores the previous DLL (mtime unchanged). Sometimes it also shows "Unable to compile custom assembly. Original version has been restored." in the trace, but a plain editor F5 compile often writes no trace line and no dialog at all, see the failure detection note below. Call `compile.errors` next for a structured error list when trace lines exist.

### Compile mechanism internals (verified live 2026-07-12)

NT8 has no programmatic compile hook. `compile.all` works only because of three things, all built into the keyboard backend:

1. Windows foreground lock timeout must be disabled (`SystemParametersInfoW` with `SPI_SETFOREGROUNDLOCKTIMEOUT` set to 0), otherwise `SetForegroundWindow` silently fails when called from a background server process and F5 never actually lands on the editor.
2. F5 must be sent as a real key press with a hold of about 80ms between key down and key up, via `keybd_event` with a scan code. A zero duration SendInput F5 with down and up batched together is dropped by NT8's WPF hotkey binding.
3. The NinjaScript Editor must have a document open in a tab. F5 on a blank editor with no open script does nothing. Open any script once, by double clicking it in the NinjaScript Explorer, and the tab persists for the rest of the NT8 session.

Before relying on `compile.all`, make sure at least one script tab is open in the editor. `compile.all` itself focuses the editor window, clicks into the code pane so keyboard focus lands in the text area, and sends the held F5.

The first time NT8 sees a new or changed AddOn, for example right after `bin\deploy_addon.ps1`, pressing F5 pops a modal Warning dialog: "NinjaTrader has detected new add on(s): AntigravityBridgeAddOn. Please ensure these are from trusted sources before compiling. Do you wish to authorize these add ons?" with Yes and No buttons. This silently blocks the compile until answered. `compile.all` auto detects this dialog and clicks Yes, `metadata.addon_authorized` in the response reflects whether it fired.

### Compile failure detection (verified live 2026-07-12)

A good compile is reliable and takes about 3 to 4 seconds, `compile.all` returns `ok: true` with `dll_mtime_before` and `dll_mtime_after` different. A failed compile writes NOTHING to disk, NT8 silently restores the previous DLL, shows no dialog, and in practice produces no trace or log line for a plain editor F5 compile. So failure is detected as "no new assembly appeared within the timeout window", `compile.all` returns `ok: false`, `error_code: ERR_COMPILE_NO_NEW_ASSEMBLY`, and `metadata.screenshot` (also in `artifacts`) pointing at a capture of the editor. The editor's Errors panel in that screenshot lists each error with NinjaScript File, Error text, Code (for example `CS1002`, `CS0103`), Line, and Column, there is no other place these errors are recorded. On `ERR_COMPILE_NO_NEW_ASSEMBLY`, open the screenshot and read the errors (a vision capable model can do this directly), fix the code, and recompile. Reinforcing the existing rule, all `.cs` files compile together into one DLL, so one broken file fails the whole compile for every script, remove or fix it before anything else will compile.

## The Backtest Flow (deterministic)

`macro.compile_and_test` (and `macro.full_dev_cycle`, which wraps it) does:

1. `compile.all`. Abort with the compile errors if it fails.
2. Record timestamp T0 (UTC ISO).
3. `tester.open` (Ctrl+R), `tester.configure` (keyboard steps, see below), `tester.start` (F5 in the Strategy Analyzer by default).
4. Poll `tester.status` with `{"since": T0, "strategy": <name>}` on the `file_write` backend every 5 seconds until `found` is true or `timeout_seconds` (default 300s) elapses. `found` means a `.xml` file newer than T0 appeared in `strategyanalyzerlogs\` whose filename matches the strategy name.
5. `tester.results` with the same `since`/`strategy` filter parses that xml into `{action, date, instrument, from_date, strategy_file, parameters, performance}`, where `performance` has one entry per `PerformanceUnit` (`Currency`, `Percent`, `Pips`, `Points`, `Ticks`), each a dict of metric name to `{all, long, short}` string values (`TotalNetProfit`, `ProfitFactor`, `SharpeRatio`, `MaxDrawdown`, `TotalNumTrades`, `PercentProfitable`, `NumWinningTrades`, `NumLosingTrades`, and more).
6. `chart.screenshot` for evidence.

If step 4 times out, the result carries `error_code_hint: ANALYZER_NOT_OPEN` in metadata, `failure_stage: tester_wait`, and the last poll's status. This usually means the Strategy Analyzer window was closed, not focused, or the run never actually started, check with a screenshot.

### macro.full_dev_cycle: the primary autonomous dev loop

This is the single call to reach for when writing and testing a strategy end to end.

```powershell
$code = Get-Content -Raw "C:\path\to\MyStrategy.cs"
$argsJson = @{ name = "MyStrategy"; content = $code; symbol = "ES 12-25"; from_date = "2026-01-01"; to_date = "2026-06-30" } | ConvertTo-Json -Depth 5 -Compress

& "C:\path\to\ninjatrader-control-plane\bin\nt8_command_api.ps1" -Command "macro.full_dev_cycle" -ArgsJson $argsJson -TimeoutSec 360
```

Response `metadata` (merged from the write step and the compile_and_test step) includes `steps` (one entry per sub-step with `success`), `compile` (the compile.all metadata), `backtest_stats` (the parsed analyzer xml, only present if the backtest completed), and `screenshot_path`. Check `ok` first, then `metadata.failure_stage` if it is false to see which step broke.

### tester.configure: data driven steps

`tester.configure` does not hardcode a fixed Strategy Analyzer navigation sequence in a way that can't be tuned. The default sequence lives in `runtime\backends\keyboard.py` as `TESTER_CONFIG_STEPS`:

```python
[
    {"keys": "tab", "wait_ms": 200},
    {"text": "{strategy}", "wait_ms": 300},
    {"keys": "enter", "wait_ms": 300},
]
```

Each step is one of `{"keys": "ctrl+shift+n"}` (send a key combo), `{"text": "{strategy}"}` (type text, `{strategy}`/`{instrument}`/`{from_date}`/`{to_date}` are resolved from the call's `args`, a step whose resolved text is empty is skipped), or `{"wait_ms": 300}` (pause only). `"wait_ms"` can be combined with either of the other two keys to pause after that step. Override the whole sequence per call by passing `args.steps` as a list of these objects, this lets you tune the exact tab order live against your NT8 8.1 build instead of editing source.

`tester.configure` always returns `metadata.verified: false`. This is intentional, it only proves the keys were sent to a focused Strategy Analyzer window, not that the backtest is actually configured correctly. Real verification happens later via `tester.status`/`tester.results` after `tester.start`, when a new analyzer xml file proves the run happened with those settings.

## Prerequisites (the truth, verified on this machine)

1. NinjaTrader 8.1 installed, and the user is logged in. On launch NT8 shows a Welcome/login dialog, either type a username and password into the fields or use Sign in with Google / Sign in with Apple, there is no stored password so this cannot be scripted, a human logs in once per NT8 session. After login, NT8 may also show an Auto Rollover Notification dialog (click Done, then a possible Rollover Yes/No confirm) and other startup dialogs, all GUI automation waits behind these too. If any command fails with `NT8_UNAVAILABLE` or a window search finds nothing, check whether NT8 is sitting at the login dialog or another startup dialog.
2. The bridge AddOn is deployed and compiled once: `bin\deploy_addon.ps1` copies `runtime\assets\nt8\AntigravityBridgeAddOn.cs` into `Documents\NinjaTrader 8\bin\Custom\AddOns\`, then you must open the NinjaScript Editor in NT8 with a document tab open and press F5 once by hand (or run `compile.all` after the server is up), answering the new AddOn authorization dialog if it appears, see the compile mechanism section below. **A freshly compiled AddOn does not start its HTTP listener until NT8 is restarted**, NT8 instantiates AddOns once at startup, so `addon_http` backed commands (account state, live market data, positions, addon screenshots, `bridge.status`) fail with `ERR_ADDON_TIMEOUT` (retryable) until NT8 is restarted after the first deploy and compile. The core dev loop does not need the bridge at all: `code.write`/`code.read`/`code.list`/`code.delete`/`code.search`, `compile.all`, `tester.*` via the Strategy Analyzer and analyzer xml parsing, `terminal.*` and win32 screenshots, `logs.*`, and `trade.*` via ATI OIF files all work without the bridge running. The bridge only adds live account and market data, and only after that one restart.
3. ATI must be enabled in NT8 (Control Center, Tools, Options, or the ATI settings dialog depending on version) for any `trade.*` command to work, it writes OIF files to `incoming\` that NT8 only picks up when ATI is turned on.
4. Python: the project venv already exists at `.venv\` (Python 3.14, created with `py -m venv .venv` from the project root). The runtime uses stdlib only (`ctypes`, `http.server`, `urllib`, `xml.etree.ElementTree`, `sqlite3`) plus optionally Pillow for PNG screenshot encoding (falls back to raw BMP if Pillow is missing). Nothing else needs installing, do not `pip install pywin32 pyautogui pythonnet requests`, none of those are imported anywhere in `runtime\`.
5. Start the server (see Tools above) before issuing any command.

## NinjaScript Code Writing Guidelines

### Strategy Skeleton

```csharp
#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.SuperDom;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.NinjaScript.Indicators;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class MyStrategy : Strategy
    {
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = @"My strategy description";
                Name = "MyStrategy";
                Calculate = Calculate.OnBarClose;
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = true;
                ExitOnSessionCloseSeconds = 30;
                IsFillLimitOnTouch = false;
                MaximumBarsLookBack = MaximumBarsLookBack.TwoHundredFiftySix;
                OrderFillResolution = OrderFillResolution.Standard;
                Slippage = 0;
                StartBehavior = StartBehavior.WaitUntilFlat;
                TimeInForce = TimeInForce.Gtc;
                TraceOrders = false;
                RealtimeErrorHandling = RealtimeErrorHandling.StopCancelClose;
                StopTargetHandling = StopTargetHandling.PerEntryExecution;
                BarsRequiredToTrade = 20;
                IsInstantiatedOnEachOptimizationIteration = true;

                // Custom parameters
                Period = 14;
            }
            else if (State == State.Configure)
            {
                // Add data series, indicators
            }
            else if (State == State.DataLoaded)
            {
                // Indicators are ready here
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < BarsRequiredToTrade)
                return;

            // Trading logic here
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Period", Order = 1, GroupName = "Parameters")]
        public int Period { get; set; }
        #endregion
    }
}
```

### Indicator Skeleton

```csharp
#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.SuperDom;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class MyIndicator : Indicator
    {
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = @"My indicator description";
                Name = "MyIndicator";
                Calculate = Calculate.OnBarClose;
                IsOverlay = false;
                DisplayInDataBox = true;
                DrawOnPricePanel = false;
                ScaleJustification = NinjaTrader.Gui.Chart.ScaleJustification.Right;
                IsSuspendedWhileInactive = true;

                Period = 14;

                AddPlot(Brushes.DodgerBlue, "MainPlot");
            }
            else if (State == State.Configure)
            {
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < Period)
                return;

            MainPlot[0] = Close[0]; // Replace with actual calculation
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Period", Order = 1, GroupName = "Parameters")]
        public int Period { get; set; }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> MainPlot
        {
            get { return Values[0]; }
        }
        #endregion
    }
}
```

### OnStateChange Lifecycle

```
SetDefaults     Set Name, Description, defaults. Called FIRST, even in grid.
Configure       Add data series (AddDataSeries), set up indicators.
DataLoaded      BarsArray populated. Safe to reference indicators.
Historical      Processing historical data (backtesting).
Realtime        Live market data flowing.
Terminated      Cleanup. Dispose resources here.
```

### Namespace Conventions

| Type | Namespace |
|---|---|
| Strategy | `NinjaTrader.NinjaScript.Strategies` |
| Indicator | `NinjaTrader.NinjaScript.Indicators` |
| AddOn | `NinjaTrader.NinjaScript.AddOns` (or custom) |
| DrawingTool | `NinjaTrader.NinjaScript.DrawingTools` |

Class name must match the file name exactly, this is enforced by `code.write_*`, which appends `.cs` to `name` and writes it verbatim, if the class name inside `content` doesn't match, compile will fail.

### Order Entry Methods

```csharp
EnterLong(int quantity, string signalName);
EnterShort(int quantity, string signalName);
ExitLong(string signalName, string fromEntrySignal);
ExitShort(string signalName, string fromEntrySignal);
SetStopLoss(CalculationMode mode, double value);
SetProfitTarget(CalculationMode mode, double value);
SetTrailStop(CalculationMode mode, double value);
```

### Built-in Indicator Access

```csharp
SMA(14)[0]                   // Simple Moving Average, current bar
EMA(20)[0]                   // Exponential Moving Average
RSI(14, 3)[0]                // RSI with smoothing
MACD(12, 26, 9).Default[0]   // MACD line
MACD(12, 26, 9).Avg[0]       // Signal line
MACD(12, 26, 9).Diff[0]      // Histogram
Bollinger(2, 14).Upper[0]    // Bollinger upper band
Bollinger(2, 14).Lower[0]    // Bollinger lower band
ATR(14)[0]                   // Average True Range
ADX(14)[0]                   // ADX
CCI(14)[0]                   // Commodity Channel Index
Stochastics(7, 14, 3).D[0]   // Stochastic %D
Stochastics(7, 14, 3).K[0]   // Stochastic %K
VWAP()[0]                    // VWAP
VOL()[0]                     // Volume
MIN(Low, 20)[0]              // Lowest low over 20 bars
MAX(High, 20)[0]             // Highest high over 20 bars
```

### Drawing Methods

```csharp
Draw.HorizontalLine(this, "tag", price, Brushes.Red);
Draw.VerticalLine(this, "tag", time, Brushes.Blue);
Draw.Line(this, "tag", startBar, startPrice, endBar, endPrice, Brushes.White);
Draw.Text(this, "tag", "text", barsAgo, price, Brushes.White);
Draw.ArrowUp(this, "tag", barsAgo, price, Brushes.Green);
Draw.ArrowDown(this, "tag", barsAgo, price, Brushes.Red);
Draw.Diamond(this, "tag", barsAgo, price, Brushes.Yellow);
Draw.Dot(this, "tag", barsAgo, price, Brushes.Cyan);
Draw.Rectangle(this, "tag", startBar, startPrice, endBar, endPrice, Brushes.Gray);
Draw.Region(this, "tag", startBar, endBar, series1, series2, null, Brushes.Blue, 20);
```

### Property Attributes

```csharp
[NinjaScriptProperty]                                 // Appears in strategy parameters (required for optimization)
[Display(Name="X", Order=1, GroupName="Parameters")]  // Display in UI
[Range(1, 100)]                                        // Numeric range validation
[Browsable(false)]                                     // Hide from property grid
[XmlIgnore]                                            // Exclude from serialization
```

### Bars Period Types

```
BarsPeriodType.Minute    1, 5, 15, 30, 60 minute bars
BarsPeriodType.Day       Daily bars
BarsPeriodType.Week      Weekly bars
BarsPeriodType.Month     Monthly bars
BarsPeriodType.Tick      Tick bars (e.g., 233 tick)
BarsPeriodType.Volume    Volume bars (e.g., 1000 volume)
BarsPeriodType.Range     Range bars (e.g., 4 range)
BarsPeriodType.Second    Second bars
BarsPeriodType.Renko     Renko bars
```

### C# 6 syntax constraints (compiler behind NinjaScript Editor)

The NinjaScript compiler targets an older C# language level. Do not use: `out var` inline declarations (use `int x; TryParse(s, out x);`), tuples (`(int, string)` or `var t = (1, "a")`), pattern matching (`if (obj is Foo f)`, switch pattern arms), local functions, string interpolation is fine in modern NT8 8.1 builds but if a compile fails on it, fall back to `string.Format`. Stick to plain C# 5/6 style: explicit types, classic `out` params, `switch` on primitives only.

## NT8 File Paths

| Path | Purpose |
|---|---|
| `Documents\NinjaTrader 8\bin\Custom\Strategies\` | Strategy .cs files |
| `Documents\NinjaTrader 8\bin\Custom\Indicators\` | Indicator .cs files |
| `Documents\NinjaTrader 8\bin\Custom\AddOns\` | AddOn .cs files |
| `Documents\NinjaTrader 8\bin\Custom\DrawingTools\` | DrawingTool .cs files |
| `Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.dll` | Compiled output, mtime is the compile success signal |
| `Documents\NinjaTrader 8\trace\trace.YYYYMMDD.NNNNN.txt` | Trace log, compile progress and failure markers |
| `Documents\NinjaTrader 8\strategyanalyzerlogs\` | Backtest result pairs, `<Strategy>_<date>_NN.xml` plus a `.cs` source snapshot |
| `Documents\NinjaTrader 8\incoming\` | ATI OIF order command files |
| `Documents\NinjaTrader 8\outgoing\` | ATI order/position status files |
| `Documents\NinjaTrader 8\nt8bridge_port.txt` | Optional AddOn port override, read by the C# bridge at startup |
| `Documents\NinjaTrader 8\workspaces\` | Workspace XML |
| `Documents\NinjaTrader 8\log\` | NT8 journal logs |

## Safety Rules

1. Sim account only by default. All testing on Sim/Demo accounts unless the user explicitly says otherwise for that turn.
2. Never enable autotrading (`strategy.enable_autotrading`) or place a live order without the user asking for it explicitly in that exact turn.
3. Backup before overwrite: every `code.write_*` and `code.delete` writes a `.cs.bak` copy of any existing file first.
4. Never touch, edit, or delete a NinjaScript file this session did not create. Reading is fine.
5. Never fake success on a platform gap command. Report `NOT_SUPPORTED_BY_PLATFORM` and the remediation, do not silently substitute a different action and claim it worked.
6. Compile before trusting any backtest or attach step, an uncompiled change is invisible to NT8.
