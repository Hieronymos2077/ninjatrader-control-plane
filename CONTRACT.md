# Design Contract (the source of truth for this system)

Every workstream implements EXACTLY these names. Do not invent different action names.

## Empirical facts (verified on this machine, NT8 8.1.7.2, 2026-07-11)

1. NT8 data dir: `C:\Users\<you>\Documents\NinjaTrader 8`
2. Compile success signal: `bin\Custom\NinjaTrader.Custom.dll` mtime CHANGES on successful compile. On failed compile NT8 restores the previous DLL (mtime unchanged) and shows "Unable to compile custom assembly. Original version has been restored."
3. Trace files: `trace\trace.YYYYMMDD.NNNNN.txt`, line format `YYYY-MM-DD HH:MM:SS:mmm <message>`. Compile start line: `Compiling and reloading NinjaTrader.Custom...`. Editor compile hotkey is F5 (confirmed in trace: `NinjaScriptEditorHotKeys: ... Compile='F5'`).
4. Strategy Analyzer: every completed backtest writes a PAIR of files to `strategyanalyzerlogs\`: `<Strategy>_<date>_NN.cs` (source snapshot) and `<Strategy>_<date>_NN.xml` (full results). The XML root is `StrategyAnalyzerLog/StrategyAnalyzerGridEntry` and contains: Action, Date, Instrument, From, Guid, OptimizationParameters, and `SummaryPerformances` blocks per PerformanceUnit (Currency, Percent, Pips, Points, Ticks) whose `SummaryPerformancesSerialize` is a pipe-delimited list of `Name;allTrades;longTrades;shortTrades` entries (TotalNetProfit, ProfitFactor, SharpeRatio, MaxDrawdown, TotalNumTrades, PercentProfitable, NumWinningTrades, NumLosingTrades, etc.).
   THIS is the deterministic backtest completion + results mechanism: a NEW xml appearing after a start timestamp = run complete; parse it for stats.
5. NT8 platform gaps confirmed by NinjaTrader staff (open tickets SFT-977, SFT-1445, SFT-4391, SFT-4897): NO supported programmatic compile, NO headless backtest API, NO chart-open from code, NO indicator-add from AddOn, NO strategy enable from AddOn. Keyboard/GUI automation and file watching are the legitimate mechanisms. `Chart.GetScreenshot(ShareScreenshotType)` IS supported. ATI/OIF file interface IS supported.
6. NT8 subscription on this machine: Free tier, login required at launch (user logs in manually; creds may be remembered).
7. The user has REAL strategies in `bin\Custom\Strategies\` (several unrelated production strategies). NEVER modify or delete files the current request did not create. Tests NEVER touch the real NT8 data dir.

## Target command map changes (controller `_BACKEND_ACTION_MAP` + catalog)

| Command | Catalog backends (ordered) | Backend: action |
|---|---|---|
| strategy.enable_autotrading | keyboard | keyboard: toggle_autotrading |
| chart.close | addon_http, keyboard | addon_http: close_chart; keyboard: close_chart |
| market_data.get | addon_http, dll_ati | addon_http: get_market_data; dll_ati: get_market_data |
| market_data.subscribe | addon_http | addon_http: subscribe_market_data |
| account.info | addon_http, dll_ati | addon_http: get_account_info; dll_ati: buying_power |
| compile.all | keyboard | keyboard: compile (deterministic, see below) |
| compile.check | file_write | file_write: compile_status |
| compile.errors | file_write | file_write: parse_compile_errors |
| tester.configure | keyboard | keyboard: configure_tester (real implementation) |
| tester.start | keyboard | keyboard: start_tester |
| tester.status | file_write, win32 | file_write: analyzer_status; win32: capture_window |
| tester.results | file_write, win32 | file_write: analyzer_results; win32: capture_window |
| tester.list_results (NEW) | file_write | file_write: analyzer_list_results |
| system.capabilities (NEW) | (controller-level, no backend) | returns per-command implementation status |
| macro.full_dev_cycle (NEW) | auto | write -> compile -> backtest -> parsed results |

All other existing mappings stay as they are.

## New backend actions (exact names)

file_write: `compile_status`, `parse_compile_errors`, `analyzer_status`, `analyzer_results`, `analyzer_list_results`
keyboard: `close_chart`, `configure_tester`, `start_tester` (upgraded), `compile` (upgraded)
addon_http: `get_account_info`, `subscribe_market_data`
C# AddOn new routes: `GET /account/{name}/state` (real), `POST /market-data/subscribe` (real), `GET /version`, `GET /compile/probe` (reflection diagnostic), `POST /compile/trigger` (best-effort reflection compile, safe try/catch)

## Compile flow (deterministic)

keyboard `compile`:
1. Record `NinjaTrader.Custom.dll` mtime + size, and current trace file offset.
2. Ensure a NinjaScript Editor window exists (win32 title scan for "NinjaScript Editor"); if none, attempt to open one; if still none, fail fast with error_code EDITOR_NOT_OPEN and remediation text.
3. Focus editor, send F5.
4. Poll up to 120s: DLL mtime changed => success. Trace shows compile-failure text or "Unable to compile" => failure; collect error lines.
5. Return structured: `{success, duration_ms, dll_mtime_before, dll_mtime_after, trace_lines[], errors[]}`. NEVER report success without the mtime change.

## Backtest flow (deterministic completion)

macro.compile_and_test / macro.full_dev_cycle:
1. compile (above). Abort on failure with errors.
2. Record timestamp T0.
3. tester.open (Ctrl+R), tester.configure (keyboard, verified focus each step), tester.start.
4. Poll file_write `analyzer_status` with `since=T0` (checks strategyanalyzerlogs for a NEW .xml, also matching strategy name when given) until found or timeout (default 300s).
5. file_write `analyzer_results` parses that xml -> structured stats (all PerformanceUnits, primary = Currency).
6. Screenshot evidence via win32/addon.

## Envelope invariants

- ok=true ONLY when the action verifiably did its job (the audit's "truthful success" rule). GUI actions must verify (window title, file artifact, mtime) before claiming success.
- error_code taxonomy stays; add: EDITOR_NOT_OPEN, ANALYZER_NOT_OPEN, COMPILE_FAILED, COMPILE_TIMEOUT, NOT_SUPPORTED_BY_PLATFORM, ADDON_STALE (health version mismatch).
- Commands that hit confirmed platform gaps (strategy.attach/detach, chart.template_save/apply, chart.indicator_add when reflection fails) return ok=false with error_code NOT_SUPPORTED_BY_PLATFORM and a remediation hint. Honest failure, never a silent stub.

## Login support (added 2026-07-12 per user request)

The NT8 Welcome dialog blocks all automation until login. The skill must support EVERY sign-in path, not just one:
- `terminal.login` command (keyboard backend). Args:
  - method: "credentials" (default) types username into the Username field and password into the Password field then clicks Log In; "google" clicks the Sign in with Google button; "apple" clicks Sign in with Apple.
  - username, password (for credentials method). If omitted, read from env NT8_USERNAME / NT8_PASSWORD.
  - The dialog is a fixed-size WPF window titled "Welcome". Use win32 to find it, focus it, and drive fields by tab order (Username is the first field, Password second) plus Enter, OR click the SSO buttons by relative position. Verify success by polling terminal.capture until the window title changes away from "Welcome"/"Sign in"/"Authorize" to a Control Center title.
- Never store the password in the repo. Read from env or the credentials arg only. Do not log the password value.

## Hard rules (restated, zero exceptions)

- NO dash punctuation anywhere (docs, comments, commit messages, UI strings). Commas, colons, periods, parentheses. Hyphens only inside compound words.
- Never kill processes you did not start. Never kill NinjaTrader or Chrome. Tests never launch or kill NT8.
- Tests run against TEMP dirs and TEMP databases only, never against `Documents\NinjaTrader 8`.
- Never modify or delete the user's real NinjaScript files.
- No emojis in code, UI, or registry entries. No gradient backgrounds (not applicable here, stated for completeness).
- C# code must stay compatible with the NinjaScript compiler (avoid C# 7+ syntax: no out var, no tuples, no pattern matching, no local functions).
- Python code: stdlib + optional Pillow only. No new hard dependencies.
- Report absolute paths of every file changed. Include verbatim test output in reports.
