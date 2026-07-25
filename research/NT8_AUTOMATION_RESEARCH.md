# NT8 Programmatic Automation Research (2026-07-11)

Web research findings on NinjaTrader 8.1 automation surfaces. Confidence markers: CONFIRMED, PLAUSIBLE, DEAD-END.

## 1. Programmatic compile
- DEAD-END (official): no supported compile outside the NinjaScript Editor. NinjaTrader staff statement in forum thread 1215609.
- PLAUSIBLE: CrossTrade MCP (commercial) claims reflection-triggered in-process recompile from an AddOn (`compile_engine: reflection.*` vs `file_only`). No class names published. A reflection probe endpoint in our AddOn can search loaded assemblies for compile entry points at runtime and attempt them in try/catch, with keyboard F5 as guaranteed fallback.
- CONFIRMED: NinjaTrader.Custom.dll is fully regenerated on every successful compile. On failure NT8 restores the previous DLL (mtime unchanged) and shows "Unable to compile custom assembly. Original version has been restored." (thread 1042456). DLL mtime is therefore a reliable success or failure signal.
- Compile target constraints (per CrossTrade docs, matches editor behavior): C# 6 level syntax, class name must equal file name, namespace must be NinjaTrader.NinjaScript.{Indicators|Strategies|AddOns}.
- Compile error text: no documented canonical log file. Empirically discover format in `trace\*.txt` around a triggered compile.

## 2. Headless backtest
- DEAD-END (official): no supported Strategy Analyzer interface. Staff statement, ticket SFT-4391 (thread 1208172).
- PLAUSIBLE (unpublished): CrossTrade MCP claims RunStrategyBacktest drives the real Strategy Analyzer engine with bit-identical results. Proprietary.
- PLAUSIBLE (unproven): instantiating StrategyBase + BarsRequest + reading SystemPerformance from an AddOn. No public working example exists. High friction expected.
- OUR SOLUTION (empirically confirmed on this machine): GUI-drive the Strategy Analyzer, then detect completion and parse results from `Documents\NinjaTrader 8\strategyanalyzerlogs\*.xml` (full stats present, see CONTRACT.md).

## 3. Chart, indicator, strategy control from AddOn
- DEAD-END: opening a chart from code (staff, thread 1110874, ticket SFT-4897). Keyboard Ctrl+Shift+N is the way.
- DEAD-END: adding an indicator to a chart from an AddOn (staff, thread 1035266, SFT-1445). AddChartIndicator() is strategy-only, from OnStateChange State.DataLoaded.
- DEAD-END: enabling or disabling a strategy from an AddOn (staff, thread 94064, SFT-977). Reflection hack described by a community dev but no code published, extremely fragile.
- LIMITED WORKAROUND (CONFIRMED): a strategy with IsEnabled = true set in State.SetDefaults auto-enables when its workspace loads.

## 4. Chart screenshot
- CONFIRMED: `chart.GetScreenshot(ShareScreenshotType.Chart|Window)` returns RenderTargetBitmap; must run via the chart window Dispatcher. WPF RenderTargetBitmap of the chart visual does NOT capture the SharpDX chart surface (thread 1087482). PNG-encode via BitmapFrame + PngBitmapEncoder. Threads 94840, 109181 contain working patterns.

## 5. ATI / OIF and Client DLL
- CONFIRMED working in 8.1: OIF files written to `Documents\NinjaTrader 8\incoming\` as `oif*.txt` with unique names. Format semicolon-delimited, empty fields keep their semicolon: `PLACE;Sim101;6E 03-21;SELL;1;MARKET;;;GTC;;;;`. Official docs: order_instruction_files_oif.htm, automated_trading_interface_at.htm. Enable ATI in Control Center Options first.
- PLAUSIBLE: NinjaTrader.Client.dll still ships at `C:\Program Files\NinjaTrader 8\bin\` per dll_interface.htm, TCP 36973.
