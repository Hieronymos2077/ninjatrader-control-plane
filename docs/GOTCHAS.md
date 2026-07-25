# Gotchas

Known pitfalls and silent failures in NT8 API automation. Read this to avoid wasting time on dead ends.

---

## Login wall

### NT8 blocks everything until a human logs in
On launch, NT8 8.1 shows a Welcome/login dialog. No command in this skill, including `terminal.launch`, can get past it. The dialog offers username and password fields, or Sign in with Google / Sign in with Apple, none of it is scripted, someone has to click through it once per NT8 session. The password is not stored for unattended relaunch on this account. If `terminal.detect` reports NT8 running but every other command times out or finds no windows, the process is almost certainly sitting at that login dialog waiting for a human.

### Startup dialogs after login also block automation
Even after login, NT8 can show an Auto Rollover Notification dialog (click Done, then a possible follow up Rollover Yes/No confirm) and other one time startup dialogs. GUI automation waits behind all of these exactly like the login dialog, a human should click through any startup dialog before expecting `compile.all`, `chart.*`, or `tester.*` to work.

---

## Compilation

### No CLI Compiler
NinjaTrader 8 has NO command line compiler. You cannot invoke `csc.exe` or `msbuild` to compile NinjaScript. The ONLY way to compile is pressing F5 in the NinjaScript Editor. The `compile.all` command handles this via keyboard simulation, but a NinjaScript Editor window must exist first (it does not need to be focused, `compile.all` finds and focuses it itself; if none exists it tries to open one from the Control Center via Ctrl+N).

### F5 is fragile, three things are required for it to actually land (verified live 2026-07-12)
1. Windows foreground lock timeout must be disabled (`SystemParametersInfoW` with `SPI_SETFOREGROUNDLOCKTIMEOUT` set to 0), otherwise `SetForegroundWindow` silently fails when called from a background server process and F5 never lands on the editor at all.
2. F5 must be sent as a real key press with a hold of about 80ms between key down and key up, via `keybd_event` with a scan code. A zero duration SendInput F5 with down and up batched together is dropped by NT8's WPF hotkey binding.
3. The editor must have a document open in a tab. F5 on a blank editor with no open script does nothing. Open any script once, by double clicking it in the NinjaScript Explorer, the tab persists for the rest of the session.

All three are built into the keyboard backend already, this is documented here so anyone extending or debugging `compile.all` understands why simple SendInput style F5 automation does not work against NT8's WPF hotkey binding.

### New AddOn authorization dialog silently blocks compile
The first time NT8 sees a new or changed AddOn, for example right after `bin\deploy_addon.ps1`, pressing F5 pops a modal Warning dialog: "NinjaTrader has detected new add on(s): AntigravityBridgeAddOn. Please ensure these are from trusted sources before compiling. Do you wish to authorize these add ons?" with Yes and No buttons. If nothing answers it, the compile just sits there, mtime never changes, and it looks like a hang or a silent failure. `compile.all` auto detects this dialog and clicks Yes, check `metadata.addon_authorized` to see whether it fired on a given call.

### DLL mtime is the only proof of success, and failure leaves no trace at all
`compile.all` records `NinjaTrader.Custom.dll`'s mtime before sending F5, then polls for the mtime to change. A good compile is reliable and takes about 3 to 4 seconds. Never trust the absence of an error as proof of success, only the mtime change counts. On a plain editor F5 compile, a failure often produces no trace line and no dialog at all, NT8 just silently restores the previous DLL. So `compile.all` treats "no new assembly within the timeout window" as the failure signal itself, returning `error_code ERR_COMPILE_NO_NEW_ASSEMBLY` plus `metadata.screenshot`, a capture of the editor's Errors panel (NinjaScript File, Error text, Code such as `CS1002`/`CS0103`, Line, Column), since that panel is the only place NT8 records the error detail for this compile path.

### NT8 restores the previous DLL on a failed compile
On compile failure, NT8 does not leave a broken DLL in place, it restores the prior working `NinjaTrader.Custom.dll` (mtime unchanged). It sometimes prints "Unable to compile custom assembly. Original version has been restored." to the trace log, but do not rely on that line appearing, treat mtime-unchanged as the reliable signal, there is no in-between state to worry about.

### All .cs Files Compile Together
Every `.cs` file in `Documents\NinjaTrader 8\bin\Custom\` compiles into a single DLL, `NinjaTrader.Custom.dll`. One syntax error in ANY file breaks compilation for ALL files, including the user's existing strategies (several unrelated production strategies). If you get unexpected compile errors, check whether another `.cs` file was recently touched. Confirmed live, when iterating on a strategy, a broken file must be removed or fixed before anything else in the project will compile again, there is no partial or per file compile.

### EDITOR_NOT_OPEN and how to fix it
If `compile.all` cannot find a NinjaScript Editor window and cannot open one from the Control Center (for example because NT8 itself is not running, or is at the login dialog, or the Control Center window is not open), it fails fast with `error_code EDITOR_NOT_OPEN`. Remediation: in NinjaTrader, open the Control Center menu, choose New, then NinjaScript Editor, and retry.

---

## Charts

### Cannot Open Charts from Code
There is NO public API to open a new chart (confirmed by NinjaTrader staff, ticket SFT-4897). The only reliable method is the keyboard shortcut Ctrl+Shift+N from the Control Center, then typing the symbol and pressing Enter. `chart.open` automates exactly this and is `best_effort`, not `working`, because it depends on window focus timing.

### ChartControl.BarsPeriod is Read-Only
You cannot programmatically change a chart's timeframe after it is created. `chart.switch_timeframe` types the new period directly into the focused chart's timeframe box instead.

### Indicator Add Uses Reflection
Adding indicators to a chart programmatically requires calling private/internal methods on `ChartControl` via .NET reflection inside the AddOn. This is fragile and can break on NT8 updates, which is why `chart.indicator_add`/`chart.indicator_remove` are `best_effort`, not `working`.

### SharpDX Rendering
NT8 charts use SharpDX (DirectX) for rendering. The Win32 `PrintWindow` API can return blank/solid captures for chart areas because DirectX surfaces do not always respond to GDI capture the same way normal WPF content does. `terminal.capture` (win32 backend) samples every 7th pixel and flags `possibly_blank: true` in its metadata when over 97 percent of sampled pixels share one value, use this flag, do not assume a capture succeeded just because a file was written. Prefer `chart.screenshot` (addon_http, uses NT8's own `Chart.GetScreenshot`) for chart content specifically.

---

## Strategy Analyzer

### No Strategy Analyzer API
The Strategy Analyzer is completely GUI based (confirmed by NinjaTrader staff, ticket SFT-4391). There is no API, no COM interface, no file based input for configuring or starting a run. `tester.open`, `tester.configure`, `tester.start` are all keyboard automation and are `best_effort`.

### Analyzer xml pairs are the real completion and results mechanism
Every completed backtest writes a PAIR of files to `Documents\NinjaTrader 8\strategyanalyzerlogs\`, `<Strategy>_<date>_NN.cs` (a source snapshot) and `<Strategy>_<date>_NN.xml` (full results). `tester.status` watches for a new `.xml` file newer than a `since` timestamp whose name matches the strategy filter, that is how a run's completion is detected deterministically instead of by a fixed sleep. `tester.results` then parses that same xml. The xml root is `StrategyAnalyzerLog/StrategyAnalyzerGridEntry`, with `SummaryPerformances` blocks per `PerformanceUnit` (`Currency`, `Percent`, `Pips`, `Points`, `Ticks`) whose `SummaryPerformancesSerialize` text is a pipe delimited list of `Name;allTrades;longTrades;shortTrades` entries.

### tester.configure and tester.start never verify anything themselves
Both return `metadata.verified: false` by design. They only prove keys were sent to a focused Strategy Analyzer window, not that the configuration took or the run actually started. Only a new analyzer xml appearing later, via `tester.status`, proves anything really happened.

### Strategy Analyzer Window State
The Strategy Analyzer must be open and focusable for keyboard automation to work. If `tester.configure` or `tester.start` cannot find a window titled "Strategy Analyzer", they fail fast with `error_code ANALYZER_NOT_OPEN` and remediation text pointing at `tester.open` (Ctrl+R).

---

## Windows / Process

### WPF Window Class
NT8 is a WPF application. Window handles use `HwndWrapper` class names, not standard Win32 classes like `EDIT` or `BUTTON`. Win32 window enumeration works fine for finding windows by title (which is what this skill does), but do not expect classic Win32 child control enumeration to find WPF controls inside them.

### NT8 Process Name
The process is `NinjaTrader` (not `NinjaTrader8`). The executable is `NinjaTrader.exe` at `C:\Program Files\NinjaTrader 8\bin\NinjaTrader.exe` by default. `terminal.detect` enumerates processes by that exe name.

### No Command Line Arguments
NT8 has essentially no useful CLI arguments for scripting. You cannot pass symbols, timeframes, or scripts via command line, `terminal.launch` just starts the exe with no arguments.

---

## AddOn / Bridge

### Deployed source and compiled bridge can drift, this is ADDON_STALE
`bin\deploy_addon.ps1` only copies the `.cs` source file into `Documents\NinjaTrader 8\bin\Custom\AddOns\`. If you edit `runtime\assets\nt8\AntigravityBridgeAddOn.cs`, redeploy, but forget to recompile (F5 in the NinjaScript Editor), NT8 keeps running the OLD compiled bridge. The running bridge's `GET /version` response (`addon_http` action `get_version`) reports a `version` string baked in at compile time (the `BridgeVersion` constant in the C# source, currently `"2.0.0"`), so if the deployed source's `BridgeVersion` differs from what `/version` actually reports, the compiled bridge is stale. `error_code ERR_ADDON_STALE` maps to this situation in the server's error taxonomy. Fix: run `compile.all` again after any AddOn source change, do not assume `deploy_addon.ps1` alone updates the running server.

### Port config file
The bridge reads `Documents\NinjaTrader 8\nt8bridge_port.txt` at startup to pick its listen port, falling back to the hardcoded default 8089 if the file is missing or invalid. If you change this file, also update `NT8_ADDON_PORT` (or `-AddonPort` on `start_nt8_api_server.ps1`) so the Python `addon_http` backend dials the same port, otherwise every addon_http command will time out even though the bridge is healthy.

### AddOn Starts on ControlCenter Window
The AddOn's `OnWindowCreated` fires for each NT8 window and only starts the HTTP listener the first time a `ControlCenter` window appears, guarded by a `_running` flag so it will not double start across multiple workspace windows.

### A freshly compiled AddOn needs NT8 restarted before its listener starts (verified live 2026-07-12)
NT8 instantiates AddOn classes once at startup. If the bridge AddOn is deployed and compiled while NT8 is already running, the new or changed AddOn class exists inside `NinjaTrader.Custom.dll` but NT8 never instantiates it, so `OnWindowCreated` never fires and the HTTP listener never starts. Every `addon_http` backed command (`chart.list`, `chart.indicator_add`, `chart.screenshot`, `account.info`, `market_data.*`, `strategy.list_running`, `bridge.status`) fails with `ERR_ADDON_TIMEOUT` (retryable) until NT8 itself is restarted. This only matters right after the first deploy or after changing the AddOn's source, restart NT8 once after that compile and the listener comes up normally on the next Control Center window. The core dev loop (code, compile, tester, terminal, logs, trade via ATI) does not depend on the bridge at all and works before that restart.

### Dispatcher.InvokeAsync for UI Operations
Any AddOn code that touches chart objects, indicators, or UI elements must run on the WPF dispatcher thread. Calling UI methods from the HTTP listener thread throws `InvalidOperationException` or silently corrupts state, this is why every UI touching route in the bridge marshals back onto the Control Center's dispatcher.

---

## ATI / Trading

### DLL ATI is Polling-Based
The file based ATI mechanism (OIF files in `incoming\`, status files in `outgoing\`) provides no callbacks or push notifications. To check order status, `order.status`/`position.get` re-read the relevant file in `outgoing\` each call, there is no event stream.

### ATI TCP Port
The ATI interface listens on TCP port 36973. This port is fixed and not configurable. This skill does not dial that TCP port directly, it uses the file based OIF mechanism instead, which requires ATI to be enabled in NT8's options.

### ATI must be explicitly enabled
`trade.*` commands write OIF files regardless of whether ATI is turned on in NT8, the write always "succeeds" as a file write. But NT8 only actually acts on them if ATI is enabled in Control Center options. A silently ignored order file is the most likely explanation if `trade.place` reports success but no order appears in NT8.

### Account Name Format
ATI account names must match exactly as they appear in NT8. Common formats: `Sim101` (simulation), `Playback101` (playback/replay), or broker specific names for live accounts.

---

## File Paths

### Documents Folder May Vary
NT8 data lives in `Documents\NinjaTrader 8\`, but "Documents" may resolve to `C:\Users\<user>\Documents\NinjaTrader 8\` or `C:\Users\<user>\OneDrive\Documents\NinjaTrader 8\` if OneDrive has taken over the Documents folder. Every backend that touches the filesystem probes both locations and prefers the plain `Documents` path if it exists; on this machine it resolves to `C:\Users\<you>\Documents\NinjaTrader 8`.

### Template XML Format
Chart and indicator templates are XML files containing serialized WPF state, GUIDs, and binary encoded settings. Modifying them by hand is risky, and in any case `chart.template_save`/`chart.template_apply` are confirmed platform gaps, always use the NT8 GUI (right click chart, Templates) for templates.

---

## General

### Name Collisions
Do not name a strategy or indicator the same as a built in NinjaScript type. Naming a strategy `SMA` collides with the built in SMA indicator and causes compile errors.

### Case Sensitivity
Strategy and indicator names are case sensitive. `MyStrategy` and `mystrategy` are different. The file name (which `code.write_strategy`/`code.write_indicator` derive from the `name` arg) must match the class name inside `content` exactly.

### IsInstantiatedOnEachOptimizationIteration
If this property is `true` (the default), the strategy is re-instantiated for each optimization iteration. Set it to `false` if the strategy has expensive initialization in `State.DataLoaded` that does not depend on optimization parameters.

### BarsRequiredToTrade
Always set this to at least the maximum lookback period of any indicator in use. Using `SMA(50)` without `BarsRequiredToTrade >= 50` causes `IndexOutOfRangeException` on historical data.
