# NT8 API Skill -- Adversarial Code Audit Report

**Date:** 2026-04-05
**Scope:** the whole runtime tree of this repository
**Verdict:** Partially functional. File-based operations will work. Keyboard, AddOn HTTP, and DLL/ATI backends have critical issues that will prevent end-to-end operation without fixes.

---

## 1. Critical Issues (Will Prevent the Skill From Working)

### CRIT-1: Backend name mismatch -- Win32 backend registered as "win32_capture" but controller expects "win32"

**File:** `runtime\backends\win32_capture.py`, line 134
**File:** `runtime\controller.py`, lines 462-467

The `Win32CaptureBackend` class has `name = "win32_capture"`, but the controller's `_BACKEND_ACTION_MAP` and `NT8_COMMAND_CATALOG` reference the backend as `"win32"`. When the controller does `self.backends.get("win32")`, it will never find the backend unless it's registered with key `"win32"` in the backends dict. However, the class `name` attribute mismatch means health checks will report `"win32_capture"` in driver fields.

**Impact:** If the backends dict is built using `backend.name` as the key (likely), all `terminal.*` commands, `chart.screenshot` (win32 path), and `tester.status`/`tester.results` (win32 path) will fail with "backend 'win32' not registered".

**Fix:** Change `Win32CaptureBackend.name` to `"win32"`, or ensure the registration code maps it to `"win32"`.

### CRIT-2: Keyboard backend calls `_ensure_nt8_focus` which imports from `win32_capture` -- circular dependency risk and wrong import path

**File:** `runtime\backends\keyboard.py`, line 198

```python
from .win32_capture import _find_nt8_windows, _get_window_title, SW_RESTORE
```

This import is inside a method, so it won't fail at module load. But it creates a tight coupling. More critically, `SW_RESTORE` is a module-level constant in `win32_capture.py` -- this will work. However, if run outside the package context (the `except ImportError` fallback), the relative import will fail silently because `keyboard.py`'s fallback path doesn't handle `win32_capture` imports.

### CRIT-3: 15+ addon_http backend actions referenced in `_BACKEND_ACTION_MAP` that DON'T EXIST in `AddonHttpBackend.execute()`

**File:** `runtime\controller.py`, lines 408-475
**File:** `runtime\backends\addon_http.py`, lines 33-48

The controller maps these commands to addon_http actions that the backend DOES NOT implement:

| Command | Expected Action | Exists in backend? |
|---|---|---|
| `chart.close` | `close_chart` | NO |
| `chart.template_save` | `save_template` | NO |
| `chart.template_apply` | `apply_template` | NO |
| `strategy.attach` | `attach_strategy` | NO |
| `strategy.detach` | `detach_strategy` | NO |
| `strategy.state` | `get_strategy_state` | NO |
| `tester.status` | `get_tester_status` | NO |
| `tester.results` | `get_tester_results` | NO |
| `logs.output` | `get_output` | NO (it's `get_output_log`) |

**Impact:** 9 commands that route to addon_http will fail with "Unknown action" every time.

**Fix:** Either add these handlers to `AddonHttpBackend` and corresponding routes to the C# AddOn, or fix the action name mapping.

### CRIT-4: DLL/ATI backend actions referenced in `_BACKEND_ACTION_MAP` that DON'T EXIST in `DllAtiBackend.execute()`

**File:** `runtime\controller.py`, lines 452-459
**File:** `runtime\backends\dll_ati.py`, lines 44-56

Missing actions:

| Command | Expected Action | Exists? |
|---|---|---|
| `account.info` | `buying_power` | NO |
| `account.list` | `get_accounts` | NO |
| `market_data.subscribe` | `subscribe_market_data` | NO |
| `market_data.get` | `get_market_data` | NO |

The DLL/ATI backend is file-based OIF only. It has no mechanism to query account info, subscribe to market data, or get market quotes. These operations require either the ATI COM/DLL interface or the AddOn HTTP bridge.

**Impact:** `account.info`, `account.list` (dll_ati path), `market_data.subscribe`, and `market_data.get` will all fail.

### CRIT-5: Keyboard backend is missing `configure_tester` and `start_tester` actions

**File:** `runtime\backends\keyboard.py`, lines 176-186
**File:** `runtime\controller.py`, lines 441-442

The `_BACKEND_ACTION_MAP` maps:
- `tester.configure` -> keyboard `configure_tester`
- `tester.start` -> keyboard `start_tester`

But `KeyboardBackend.execute()` dispatch table has no `configure_tester` or `start_tester` handlers. This means the entire backtest workflow (`macro.compile_and_test`, `macro.iterate_strategy`) will fail.

**Impact:** All macro commands that involve backtesting are broken.

**Fix:** Add `_configure_tester` and `_start_tester` methods to `KeyboardBackend`.

### CRIT-6: C# AddOn -- `NinjaScript.GetGeneratedStrategies()` doesn't exist

**File:** `runtime\assets\nt8\AntigravityBridgeAddOn.cs`, line 507

```csharp
var strategies = NinjaTrader.NinjaScript.NinjaScript.GetGeneratedStrategies();
```

There is no such static method on `NinjaTrader.NinjaScript.NinjaScript`. To get running strategies, you need to iterate `StrategyBase` instances via the account's strategies or use `NinjaTrader.NinjaScript.Strategy.SystemPerformance` etc. The correct approach involves `Account.Strategies` or similar.

**Impact:** `HandleGetStrategies()` will throw, returning empty results every time. The `strategy.list_running` and `strategy.state` commands will be useless.

### CRIT-7: C# AddOn -- `ChartControl.Indicators` is not a publicly accessible collection you can Add/Remove from

**File:** `runtime\assets\nt8\AntigravityBridgeAddOn.cs`, lines 282, 340-354, 689-725

`ChartControl` does not expose an `Indicators` property that is a mutable `IList<IndicatorBase>` you can call `.Add()`, `.Remove()`, or `.RemoveAt()` on. In NinjaTrader 8, indicators are added to charts through `ChartBars` and the chart panel system, typically via `AddChartIndicator()` from within a NinjaScript context or through the UI.

The `AddIndicatorToChart` method (line 689) tries:
1. `Type.GetType()` to find indicator -- this won't work because NT8 loads NinjaScript types in a custom assembly loader
2. `Activator.CreateInstance()` -- NinjaScript indicators require special initialization
3. `cc.Indicators.Add(indicator)` -- this collection is likely read-only or doesn't exist as expected
4. Reflection to call `RefreshIndicators` -- this private method may not exist

**Impact:** `chart.indicator_add`, `chart.indicator_remove`, and `chart.indicator_list` via addon_http will all fail.

### CRIT-8: C# AddOn -- `chart.GetScreenshot(ShareScreenshotType.Window)` may not exist

**File:** `runtime\assets\nt8\AntigravityBridgeAddOn.cs`, line 375

The `Chart.GetScreenshot()` method with `ShareScreenshotType` parameter exists in some NT8 versions but the exact API signature varies. In many NT8 builds, `GetScreenshot` returns a `RenderTargetBitmap`, not a `BitmapSource`. The `ShareScreenshotType.Window` enum may not exist in all versions.

**Impact:** Screenshot capture via AddOn may fail, falling back to win32 capture.

---

## 2. Major Issues (Will Cause Frequent Failures)

### MAJ-1: Keyboard compile flow has no way to verify compilation succeeded

**File:** `runtime\backends\keyboard.py`, lines 245-268

The `_compile` method sends F5 and returns `success=True` after 0.5 seconds regardless of whether compilation actually succeeded, failed, or is still running. NinjaScript compilation can take 5-30+ seconds. The method doesn't wait for completion or check the output window.

**Impact:** `compile.all` will always report success. Downstream commands that depend on compilation having finished (indicator add, strategy attach, backtest) will fail intermittently.

**Fix:** After sending F5, poll the log file or output window for "compile" messages, with a timeout.

### MAJ-2: Keyboard `_compile` sends wrong shortcut to open NinjaScript Editor

**File:** `runtime\backends\keyboard.py`, line 253

```python
_send_key_combo(_parse_key_combo("ctrl+shift+e"))
```

`Ctrl+Shift+E` in NinjaTrader 8 opens the **Simulated Data Feed settings**, not the NinjaScript Editor. The correct shortcut to open the NinjaScript Editor is `Ctrl+N` (as documented in `shortcuts.py` line 28).

**Impact:** Compile flow will open the wrong window and F5 won't trigger compilation.

**Fix:** Change to `"ctrl+n"`.

### MAJ-3: Keyboard `_open_chart` uses arg name `instrument` but catalog sends `symbol`

**File:** `runtime\backends\keyboard.py`, line 271
**File:** `runtime\controller.py`, line 92

The `chart.open` catalog requires `symbol` as a required arg. But `KeyboardBackend._open_chart` reads `args.get("instrument", "ES 09-25")`. The arg name mismatch means the user-provided symbol will be ignored and it defaults to "ES 09-25" every time.

**Impact:** `chart.open` will always open ES 09-25 regardless of what symbol is requested.

**Fix:** Change `_open_chart` to use `args.get("symbol", ...)` or `args.get("instrument", args.get("symbol", ...))`.

### MAJ-4: Keyboard `_switch_instrument` uses wrong arg name

**File:** `runtime\backends\keyboard.py`, line 294

Same issue -- reads `args["instrument"]` but catalog sends `symbol`. Will raise `KeyError`.

### MAJ-5: `chart.indicator_add` arg name mismatch between controller and addon_http backend

**File:** `runtime\controller.py`, line 121 -- catalog requires `indicator`
**File:** `runtime\backends\addon_http.py`, line 124 -- reads `args["indicator_name"]`

The controller passes `args` directly to the backend. The catalog accepts `indicator` but the backend reads `indicator_name`. Will raise `KeyError`.

**Fix:** Either rename the catalog arg to `indicator_name` or add mapping in the controller.

### MAJ-6: `chart.indicator_list` and `chart.indicator_add` require `chart_id` but it's listed as optional

**File:** `runtime\backends\addon_http.py`, lines 113, 122, 148

All indicator operations and screenshot via addon_http do `args["chart_id"]` -- a hard key access that will raise `KeyError` if `chart_id` is not provided. But the catalog lists `chart_id` as optional.

**Impact:** Calling these without `chart_id` will crash.

### MAJ-7: `logs.output` action name mismatch

**File:** `runtime\controller.py`, line 469 -- maps to `get_output`
**File:** `runtime\backends\addon_http.py`, line 47 -- registered as `get_output_log`

The addon_http dispatch table registers the action as `get_output_log`, but the controller action map sends `get_output`. Will fail with "Unknown action 'get_output'".

### MAJ-8: `compile.check` routes to keyboard `compile` action -- wrong behavior

**File:** `runtime\controller.py`, line 419

```python
"compile.check": {"keyboard": "compile", "file_write": "read_log"},
```

`compile.check` is supposed to *check* compile results, but when routed to keyboard backend, it triggers a *new* compilation (same as `compile.all`). Should route to `file_write` `read_log` only.

### MAJ-9: Win32 PrintWindow may not capture NinjaTrader's DirectX-rendered chart content

**File:** `runtime\backends\win32_capture.py`, line 271

NinjaTrader 8 uses SharpDX (DirectX) for chart rendering. `PrintWindow` with `PW_RENDERFULLCONTENT=2` may only capture WPF elements, leaving the DirectX chart area as a black rectangle. The BitBlt fallback (line 274) requires the window to be visible and unoccluded.

**Impact:** Screenshots may show empty/black chart areas. The visual verification system will produce false negatives.

### MAJ-10: C# AddOn `FindChartControl` and `FindChart` access `Application.Current.Windows` from a ThreadPool thread without dispatching to UI thread

**File:** `runtime\assets\nt8\AntigravityBridgeAddOn.cs`, lines 653-685

These methods iterate `Application.Current.Windows` directly, but they're called from inside `RunOnUi` lambdas in some places and directly in others. The `HandleRequest` method calls these from a `ThreadPool` thread. `Application.Current.Windows` must be accessed from the UI thread in WPF.

The `HandleGetIndicators` (line 276) correctly wraps in `RunOnUi`, but `FindChartControl` at line 658 directly accesses `Application.Current.Windows`. Since it's called from *within* `RunOnUi` lambdas, this is actually fine for those callers. But `HandleScreenshot` calls `FindChart` inside `RunOnUi`, so that's OK too. However, if any future code calls `FindChartControl` or `FindChart` outside `RunOnUi`, it will crash.

### MAJ-11: C# AddOn `HandleGetOutputLog` uses incorrect API

**File:** `runtime\assets\nt8\AntigravityBridgeAddOn.cs`, line 640

```csharp
var outputTab = NinjaTrader.Code.Output.Process("", PrintTo.OutputTab1);
```

`NinjaTrader.Code.Output.Process` is used to *write* to the output window, not read from it. There's no built-in API to read back the output window contents programmatically. You'd need to access the actual WPF TextBox/RichTextBox control via the visual tree.

**Impact:** `logs.output` via addon_http will return empty or incorrect data.

---

## 3. Minor Issues (Edge Cases, Cleanup)

### MIN-1: `_type_string` shift-key mapping is incomplete

**File:** `runtime\backends\keyboard.py`, line 113

```python
needs_shift = ch.isupper() or ch in '~!@#$%^&*()_+{}|:"<>?'
```

The special chars requiring shift are hardcoded and the VK codes used are for the *unshifted* version of the key. For example, typing `!` would send Shift + `1` (0x31), but `KEY_MAP["!"]` doesn't exist -- it falls through to the `VkKeyScanW` fallback. The `needs_shift` check redundantly triggers shift for chars that are already handled by the fallback's shift_state detection.

### MIN-2: `_BACKEND_ACTION_MAP["bridge.deploy"]` maps to both `file_write: write_file` and `keyboard: compile`

**File:** `runtime\controller.py`, line 474

But `bridge.deploy` is not a macro, so only one backend will be selected. The deploy command should write the AddOn file AND compile, but the current architecture only executes one backend action per command. This should be a macro.

### MIN-3: SQLite connections are not pooled in lifecycle/idempotency stores

**Files:** `lifecycle.py`, `idempotency.py`

Each method call creates a new `sqlite3.connect()`. Under high throughput, this causes connection churn. Not a real problem at expected load levels, but worth noting.

### MIN-4: `compile.errors` maps to `file_write: read_log` with no special parsing

**File:** `runtime\controller.py`, line 420

`compile.errors` is supposed to return structured errors, but it just reads the raw log file. No parsing of NinjaScript compile error format is implemented.

### MIN-5: `code.write_strategy/indicator/addon` all map to `write_file` but don't set `type` arg

**File:** `runtime\controller.py`, lines 410-412

The `FileWriteBackend._write_file` reads `args.get("type", "strategy")`. For `code.write_indicator`, the type should be "indicator" and for `code.write_addon` it should be "addon". But the controller doesn't inject the correct `type` -- it just passes args through. The user must manually include `type` in args, or everything gets written to the Strategies folder.

**Impact:** `code.write_indicator` writes to Strategies folder, not Indicators folder. Same for addons.

**This is actually a MAJOR issue. Upgrading severity.**

**Fix:** The controller should inject `{"type": "indicator"}` for `code.write_indicator`, `{"type": "addon"}` for `code.write_addon`, etc. Or the enriched_args should set this automatically.

### MIN-6: Evidence store writes to disk on every command

**File:** `runtime\server.py`, lines 605-628

Every single command execution writes a JSON manifest + response file to disk. For rapid iteration loops, this creates substantial I/O.

### MIN-7: `_macro_dispatch` is a class variable dict with unbound method references

**File:** `runtime\controller.py`, lines 928-934

```python
_macro_dispatch: dict[str, Any] = {
    "macro.develop_indicator": _macro_develop_indicator,
    ...
}
```

These are unbound functions at class definition time in Python 3. The handler is called as `handler(self, args, timeout_seconds)` on line 682, which works correctly because `self` is passed explicitly. This is fine but unusual and fragile.

---

## 4. Feasibility Assessment

### File Write Backend: WILL WORK
- NT8 data directory detection is correct (`Documents\NinjaTrader 8`)
- Path structure `bin\Custom\Strategies`, `bin\Custom\Indicators`, etc. is correct for NT8
- Writing .cs files, reading, searching, backup -- all solid
- Log reading is correct (NT8 logs in `log/` and `trace/` subdirectories)
- **BLOCKER:** Type arg not auto-set (see MIN-5) -- files go to wrong directory

### Keyboard Backend: PARTIALLY FEASIBLE, SIGNIFICANT ISSUES
- `SendInput` WILL work with NT8's WPF windows (WPF processes keyboard input normally)
- `Ctrl+Shift+N` for new chart is correct
- Compile flow has wrong shortcut (MAJ-2) and no completion detection (MAJ-1)
- Instrument/symbol arg mismatch (MAJ-3, MAJ-4) breaks chart operations
- Missing `configure_tester` and `start_tester` (CRIT-5) breaks backtest workflow
- Strategy Analyzer automation via keyboard is extremely brittle -- requires precise focus, tab order, and timing

### Win32 Capture Backend: MOSTLY FEASIBLE
- Process detection via `CreateToolhelp32Snapshot` is correct; `NinjaTrader.exe` is the right process name
- `EnumWindows` will find NT8's WPF windows correctly
- `PrintWindow` may not capture DirectX chart content (MAJ-9)
- BMP fallback writing is correctly implemented
- Window management (focus, arrange, state) will work

### AddOn HTTP Backend: PARTIALLY FEASIBLE, MISSING HANDLERS
- HTTP connection and JSON parsing work correctly
- 9 expected actions are not implemented (CRIT-3)
- The C# AddOn has multiple NT8 API issues (CRIT-6, CRIT-7, CRIT-8, MAJ-11)
- `HttpListener` on localhost is correct and will work
- Thread safety via `RunOnUi` dispatcher pattern is correct approach

### DLL/ATI Backend: PARTIALLY FEASIBLE
- OIF file format is close but may have issues with exact NT8 expectations
- File writing to `Documents\NinjaTrader 8\incoming\` is the correct path for ATI
- Missing 4 actions that are mapped in the controller (CRIT-4)
- Order status file reading from `outgoing/` is reasonable but format assumptions need verification
- The ATI file interface is a real NT8 feature, but it requires ATI to be enabled in NT8 settings

### Server: WILL WORK
- `ThreadingHTTPServer` is fine for the expected load (single AI client)
- Idempotency mechanism adds value for retry scenarios
- Evidence store is over-engineered for the use case but functional
- Lifecycle tracking is useful for debugging

### C# AddOn: WILL NOT COMPILE WITHOUT FIXES
- Multiple invalid NinjaTrader API calls (CRIT-6, CRIT-7, CRIT-8, MAJ-11)
- JSON serialization is correctly implemented
- HttpListener pattern is correct
- UI thread marshaling is correct
- Overall architecture (embedded HTTP server in AddOn) is sound

---

## 5. Missing Pieces

### MISS-1: No entry point / bootstrap script
There's no `main.py`, `run.py`, or startup script that instantiates the backends, creates the controller, and starts the server. The skill has all the components but no wiring.

### MISS-2: No way to determine compile success programmatically
After sending F5, there's no mechanism to detect when compilation finishes or whether it succeeded. Need to either:
- Poll the NT8 log file for compile completion messages
- Read the Output Window via the AddOn bridge
- Watch the NinjaScript Editor title bar for "Compiling..." -> normal title change

### MISS-3: No `configure_tester` or `start_tester` keyboard handlers
The Strategy Analyzer automation requires complex UI interaction (dropdown selection for strategy, instrument fields, date pickers, run button). This is not trivially achievable via keyboard shortcuts alone.

### MISS-4: No mechanism to detect when a backtest completes
`tester.status` routes to `addon_http: get_tester_status` (which doesn't exist) or `win32: capture_window` (which gives a screenshot, not structured data). There's no way to programmatically determine backtest progress/completion.

### MISS-5: No error log parser for compile errors
`compile.errors` just reads raw log text. Need a parser that extracts file, line number, error code, and message from NinjaScript compile output format.

### MISS-6: No `bridge.deploy` macro implementation
`bridge.deploy` maps to a single backend action, but should be a multi-step macro: write AddOn .cs file to `bin/Custom/AddOns/`, compile, wait for AddOn to start, verify HTTP bridge health.

### MISS-7: No mechanism to install the AddOn on first use
The C# AddOn file exists in `runtime/assets/nt8/` but nothing copies it to the NT8 `bin/Custom/AddOns/` directory or triggers compilation.

### MISS-8: No strategy attach/detach implementation
Neither the AddOn nor any backend implements actual strategy attachment to charts. This is one of the most important features for the AI workflow.

---

## 6. Recommendations (Prioritized Fix List)

### Priority 1 -- Get core write/compile/read loop working

1. **Fix MIN-5 (type injection):** In `controller.py`, before calling `backend.execute()`, inject the correct `type` arg for `code.write_indicator` ("indicator"), `code.write_addon` ("addon"), etc. This is a one-line fix per command.

2. **Fix MAJ-2 (wrong compile shortcut):** Change `keyboard.py` line 253 from `ctrl+shift+e` to `ctrl+n`.

3. **Fix MAJ-3/MAJ-4 (arg name mismatch):** In `keyboard.py`, change `_open_chart` to read `args.get("symbol", ...)` and `_switch_instrument` to read `args["symbol"]`.

4. **Fix MAJ-1 (compile completion detection):** After F5, poll the latest log file for "Compile completed" or similar, with a 30-second timeout.

5. **Add bootstrap/entry point script** that wires backends -> controller -> server.

### Priority 2 -- Fix backend registration and action mapping

6. **Fix CRIT-1 (backend name):** Change `Win32CaptureBackend.name` to `"win32"`.

7. **Fix CRIT-3 (missing addon_http actions):** Add stub implementations for `close_chart`, `save_template`, `apply_template`, `attach_strategy`, `detach_strategy`, `get_strategy_state`, `get_tester_status`, `get_tester_results`. Fix `get_output` -> `get_output_log` mapping.

8. **Fix CRIT-5 (missing keyboard actions):** Add `_configure_tester` and `_start_tester` to keyboard backend, or defer these to "not yet implemented" with clear errors.

9. **Fix MAJ-5 (indicator_name arg):** Normalize arg names between catalog and backends.

10. **Fix MAJ-6 (optional chart_id):** Either make `chart_id` required in the catalog, or add fallback logic in addon_http to use the first available chart.

### Priority 3 -- Fix C# AddOn

11. **Fix CRIT-6 (GetGeneratedStrategies):** Replace with iteration over `Account.All` -> `account.Strategies`.

12. **Fix CRIT-7 (Indicators collection):** Research correct NT8 API for programmatic indicator management. May need to use `ChartBars.AddIndicator()` or reflection into internal chart panel APIs.

13. **Fix MAJ-11 (Output.Process):** Remove or replace with visual tree inspection of the Output Window's text control.

14. **Add missing endpoints:** chart close, template save/apply, strategy attach/detach, tester status/results.

### Priority 4 -- Make macros reliable

15. **Convert `bridge.deploy` to a macro** that writes the AddOn file with correct type, compiles, waits, and verifies.

16. **Implement compile error parser** for structured error output from NinjaScript compilation.

17. **Add backtest completion detection** (log polling or AddOn-based status reporting).

### Priority 5 -- Address feasibility concerns

18. **Test PrintWindow capture** with actual NT8 to determine if DirectX content is captured. If not, implement alternative (e.g., `BitBlt` with window activation, or AddOn-based `GetScreenshot`).

19. **Verify OIF file format** against NT8 ATI documentation. Test with actual NT8 installation.

20. **Add ATI enabling check** -- verify that the ATI interface is enabled in NT8 settings before attempting file-based order commands.
