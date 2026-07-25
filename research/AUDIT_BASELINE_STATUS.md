# Baseline Audit of the Imported Code (2026-07-11)

Status of every issue from research/AUDIT_REPORT.md as found in THIS repo's baseline commit, plus new bugs. Produced by an independent audit agent reading the deployed copy this repo was imported from.

## Old issues: status

- CRIT-1 (win32 backend name): FIXED. win32_capture.py name = "win32".
- CRIT-2 (keyboard in-method relative import of win32_capture): still present, moot when run as package via `python -m runtime`.
- CRIT-3 (missing addon_http actions): wiring FIXED, but save_template, apply_template, attach_strategy, detach_strategy, get_tester_status, get_tester_results are hardcoded "not yet implemented" stubs in the C# AddOn (lines ~769-840).
- CRIT-4: PARTIALLY. dll_ati registers get_accounts, subscribe_market_data, get_market_data, buying_power, cash_value, realized_pnl but all route to _not_supported_via_file. Catalog restricts account.info, market_data.subscribe, market_data.get to dll_ati ONLY, so these three commands ALWAYS FAIL even though addon_http has working _get_market_data and _get_accounts.
- CRIT-5: PARTIALLY. keyboard has start_tester (blind Enter, unverified success) and configure_tester which is a stub that ALWAYS returns success=False. So macro.compile_and_test and macro.iterate_strategy always die at tester.configure (controller.py ~796-803).
- CRIT-6 (GetGeneratedStrategies): FIXED via Account.All iteration (AntigravityBridgeAddOn.cs ~575-611).
- CRIT-7 (ChartControl.Indicators mutation): unchanged reflection attempt, now fails gracefully with clear error.
- CRIT-8 (GetScreenshot): PARTIAL. RenderTargetBitmap fallback exists but only in the catch block; a null (non-throwing) GetScreenshot result never triggers the fallback (cs ~415-445).
- MAJ-1 (compile completion): FIXED with a 30s log-poll heuristic (keyboard.py 268-316). Upgrade to deterministic DLL-mtime per CONTRACT.md.
- MAJ-2 (wrong shortcut): fixed in code (ctrl+n), still wrong in bin/deploy_addon.ps1 line 53 (says Ctrl+Shift+E) and inconsistent in docs.
- MAJ-3/4 (symbol vs instrument): FIXED.
- MAJ-5: PARTIAL. _add_indicator accepts both, but _remove_indicator does hard args["indicator_name"] while catalog sends "indicator": chart.indicator_remove always raises KeyError (addon_http.py:149).
- MAJ-6 (chart_id optional): FIXED, defaults to "active", C# resolves "active" = first chart.
- MAJ-7 (get_output alias): FIXED.
- MAJ-8 (compile.check retrigger): FIXED.
- MAJ-9 (PrintWindow DirectX blank): still present, no blank-detection.
- MAJ-10: fixed in practice (all call sites use RunOnUi).
- MAJ-11 (output read): FIXED, reads UserDataDir/log tail via File.ReadAllLines.
- MIN-1 shift-map: present. MIN-3 sqlite conn churn: present. MIN-4 no compile error parser: present. MIN-5 type injection: FIXED (controller ~552-557). MIN-6 evidence writes every command: present. MIN-7 macro dispatch dict: present, works.
- MISS-1 entry point: FIXED (runtime/__main__.py). MISS-2: fixed (heuristic). MISS-3: partial (configure_tester stub). MISS-4 backtest completion: MISSING (solved by CONTRACT.md analyzer xml approach). MISS-5 error parser: missing. MISS-6/7 bridge.deploy macro: FIXED (controller ~930-962). MISS-8 strategy attach: stub.

## New bugs found in baseline (fix all)

1. strategy.enable_autotrading maps to keyboard "send_keys" with no "keys" arg -> guaranteed KeyError. Working _toggle_autotrading (keyboard.py ~415-427) is dead code. Map to toggle_autotrading.
2. chart.close keyboard fallback maps to "send_keys" with no "keys" -> KeyError. Needs keyboard close_chart action.
3. market_data.get/subscribe: working addon_http handlers unreachable due to catalog gating (see CRIT-4).
4. HandleScreenshot: null GetScreenshot never triggers RenderTargetBitmap fallback.
5. account.info, market_data.subscribe, market_data.get: 100 percent failure commands via catalog.
6. macro.compile_and_test and macro.iterate_strategy always fail at tester.configure.
7. bin/deploy_addon.ps1 documents wrong shortcut (Ctrl+Shift+E).
8. Docs hardcoded a stale absolute path from an earlier location of this project in every command example. They now reference the project root relatively.
9. docs/OPERATIONS_QUICKSTART.md tells operator to pip install pywin32 pyautogui pillow pythonnet requests. Actual code uses ONLY stdlib ctypes + optional Pillow.
10. bin/start_nt8_api_server.ps1 runs `python runtime/server.py` which has NO main block: process exits 0 instantly while the script reports "Server started with PID". Correct: `python -m runtime` from the project root (or runtime/__main__.py). MOST SEVERE surviving bug.
11. C# Port = 8089 is a compile-time constant while Python reads NT8_ADDON_PORT env var: silent divergence possible. C# should read an optional port config file.

## Command status table (baseline)

Working: code.* (all 7), compile.all/check/errors (heuristic), chart.list/open/switch_instrument/switch_timeframe/indicator_list/screenshot, strategy.list_running/state, tester.open, trade.* (5, OIF unverified fills), account.list (addon), position.get/list, order.list/status, market_data.history, terminal.* (6), logs.* (3), bridge.status/deploy, macro.chart_open_robust.
Stubs (clean fail): chart.template_save/apply, strategy.attach/detach, tester.status/results (addon path), tester.configure.
Broken (crash or guaranteed fail): chart.indicator_remove, strategy.enable_autotrading, chart.close (keyboard path), account.info, market_data.get, market_data.subscribe, macro.compile_and_test, macro.iterate_strategy.

## C# AddOn routes (baseline)

Real: /health, /charts, /chart/{id}/indicators, /chart/{id}/indicator/add (unreliable API), /chart/{id}/indicator/remove, /chart/{id}/screenshot, /accounts, /positions, /orders, /strategies, /market-data/{instrument}, /market-data/history, /connections, /logs/output, /chart/{id}/close, /strategy/{name}/state.
Stubs: /chart/{id}/template/save, /chart/{id}/template/apply, /strategy/attach, /strategy/detach, /tester/status, /tester/results.
