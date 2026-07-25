# Recipes

Copy paste command sequences for the NT8 API skill. Each recipe shows the PowerShell CLI form, `$api` below always means:

```powershell
$api = "C:\path\to\ninjatrader-control-plane\bin\nt8_command_api.ps1"
```

---

## The full autonomous dev loop: macro.full_dev_cycle

This is the one call to reach for by default: write a strategy, compile it, backtest it, get parsed results back, all in one round trip.

```powershell
$code = @"
using System;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Indicators;

namespace NinjaTrader.NinjaScript.Strategies
{
    public class SmaCrossover : Strategy
    {
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "SmaCrossover";
                Calculate = Calculate.OnBarClose;
                BarsRequiredToTrade = 50;
                FastPeriod = 10;
                SlowPeriod = 30;
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < BarsRequiredToTrade) return;

            if (CrossAbove(SMA(FastPeriod), SMA(SlowPeriod), 1))
                EnterLong(1, "SmaLong");
            else if (CrossBelow(SMA(FastPeriod), SMA(SlowPeriod), 1))
                EnterShort(1, "SmaShort");
        }

        [NinjaScriptProperty]
        [Range(1, 200)]
        [Display(Name = "Fast Period", Order = 1, GroupName = "Parameters")]
        public int FastPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(1, 200)]
        [Display(Name = "Slow Period", Order = 2, GroupName = "Parameters")]
        public int SlowPeriod { get; set; }
    }
}
"@

$argsJson = @{
    name       = "SmaCrossover"
    content    = $code
    symbol     = "ES 12-25"
    from_date  = "2026-01-01"
    to_date    = "2026-06-30"
} | ConvertTo-Json -Depth 5 -Compress

& $api -Command "macro.full_dev_cycle" -ArgsJson $argsJson -TimeoutSec 360
```

Response `metadata.backtest_stats.performance.Currency` has `TotalNetProfit`, `ProfitFactor`, `TotalNumTrades`, `MaxDrawdown`, and more, each shaped `{"all": "...", "long": "...", "short": "..."}`. Check `ok` first, if false look at `metadata.failure_stage` (`write_strategy`, `compile`, `tester_configure`, `tester_start`, `tester_wait`) to see exactly where it broke.

### HTTP equivalent

```bash
curl -X POST http://localhost:8088/v1/nt8/command \
  -H "Content-Type: application/json" \
  -d '{"command": "macro.full_dev_cycle", "args": {"name": "SmaCrossover", "content": "...", "symbol": "ES 12-25", "from_date": "2026-01-01", "to_date": "2026-06-30"}, "timeout_seconds": 360}'
```

---

## Iterate on an existing strategy: macro.iterate_strategy

Compares the new run against the strategy's most recent prior backtest automatically.

```powershell
$modifiedCode = "... updated .cs content, same class name ..."

$argsJson = @{
    name    = "SmaCrossover"
    content = $modifiedCode
    symbol  = "ES 12-25"
    from_date = "2026-01-01"
    to_date   = "2026-06-30"
} | ConvertTo-Json -Depth 5 -Compress

& $api -Command "macro.iterate_strategy" -ArgsJson $argsJson -TimeoutSec 360
```

Response `metadata.before` is the prior run's stats (from `tester.list_results`, `null` if there was no prior run), `metadata.after` is the new run's stats. Same structure as `macro.compile_and_test`'s `backtest_stats`.

---

## Compile-only loop (fast iteration without a backtest)

Use this while getting the code to compile clean, before spending the ~1 to 5 minutes a full backtest takes. Before the first call this session, make sure a script tab is already open in the NinjaScript Editor, double click any script in the NinjaScript Explorer once, F5 does nothing on a blank editor with no document open, and the tab persists for the rest of the session.

```powershell
& $api -Command "code.write_strategy" -ArgsJson (@{ name = "MyStrategy"; content = $code } | ConvertTo-Json -Compress)
& $api -Command "compile.all"
```

A good compile is reliable and takes about 3 to 4 seconds, `ok: true` with `metadata.dll_mtime_before` and `metadata.dll_mtime_after` different is the only proof. If this is the first compile right after `bin\deploy_addon.ps1`, or after the AddOn source changed, NT8 pops a new AddOn authorization Warning dialog before it will compile at all, `compile.all` answers Yes automatically, check `metadata.addon_authorized` to confirm it fired.

If `compile.all`'s `ok` is false with `error_code: ERR_COMPILE_NO_NEW_ASSEMBLY`, NT8 wrote nothing to disk (it silently restores the previous DLL and shows no dialog and usually no trace line), so the errors only exist in the editor's Errors panel. `metadata.screenshot` (also listed in `artifacts`) is a capture of that panel, listing NinjaScript File, Error text, Code (for example `CS1002`, `CS0103`), Line, and Column for each error, open it (a vision capable model can read it directly) to see what broke:

```powershell
& $api -Command "compile.errors"
```

`compile.errors` returns `metadata.errors`, a list of `{file, line, code, message, source}` (or `{raw, source}` for the generic "Unable to compile" marker line when a trace line did exist), but for a plain editor F5 failure the trace is often empty, the screenshot from `compile.all`'s response is the primary source of truth. Fix the code, `code.write_strategy` again (this overwrites, backing up the old version to `.cs.bak` first), `compile.all` again. Repeat until `ok` is true, proven by the DLL mtime actually changing, not by the absence of errors. Remember all `.cs` files compile together into one DLL, a broken file blocks every script's compile until it is fixed or removed.

---

## Write and compile a simple indicator

```powershell
$code = @"
using System;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Indicators;

namespace NinjaTrader.NinjaScript.Indicators
{
    public class PriceDeviation : Indicator
    {
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "PriceDeviation";
                Calculate = Calculate.OnBarClose;
                IsOverlay = false;
                Period = 20;
                AddPlot(Brushes.DodgerBlue, "Deviation");
                AddLine(Brushes.Gray, 0, "Zero");
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < Period) return;
            double sma = SMA(Period)[0];
            Deviation[0] = ((Close[0] - sma) / sma) * 100;
        }

        [NinjaScriptProperty]
        [Range(1, 500)]
        [Display(Name = "Period", Order = 1, GroupName = "Parameters")]
        public int Period { get; set; }

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> Deviation { get { return Values[0]; } }
    }
}
"@

& $api -Command "code.write_indicator" -ArgsJson (@{ name = "PriceDeviation"; content = $code } | ConvertTo-Json -Compress)
& $api -Command "compile.all"
```

Or in one call via `macro.develop_indicator`, which also opens a chart, adds the indicator, and screenshots:

```powershell
$argsJson = @{ name = "PriceDeviation"; content = $code; symbol = "NQ 12-25" } | ConvertTo-Json -Depth 5 -Compress
& $api -Command "macro.develop_indicator" -ArgsJson $argsJson -TimeoutSec 120
```

---

## Chart evidence capture

```powershell
& $api -Command "chart.open" -ArgsJson '{"symbol": "ES 12-25"}'
Start-Sleep -Seconds 2
& $api -Command "chart.list"
& $api -Command "chart.screenshot" -ArgsJson '{"name": "my_evidence"}'
```

`chart.screenshot` (backend `addon_http`, action `screenshot`) uses NT8's own `Chart.GetScreenshot`, which correctly renders the SharpDX chart surface, unlike a raw Win32 window capture. If `addon_http` is unavailable (bridge not compiled or NT8 not running), the catalog falls back to `win32`'s `capture_window`, which is a plain `PrintWindow` grab and can come back blank for the chart area, check `metadata.possibly_blank` on that fallback path.

For a full application window instead of just the chart surface:

```powershell
& $api -Command "terminal.capture" -ArgsJson '{"name": "full_window"}'
```

---

## Honest handling of platform gaps

`strategy.attach`, `strategy.detach`, `chart.template_save`, `chart.template_apply` have no supported NT8 API. Calling them always returns `ok: false`, `error_code: ERR_NOT_SUPPORTED_BY_PLATFORM`:

```powershell
& $api -Command "strategy.attach" -ArgsJson '{"strategy": "SmaCrossover", "symbol": "ES 12-25"}'
```

```json
{
  "ok": false,
  "error_code": "ERR_NOT_SUPPORTED_BY_PLATFORM",
  "result": {"success": false, "stderr": "..."},
  "..."
}
```

Do not retry this, do not try a different backend, there is none. The correct move is one of:
1. Attach the strategy manually from the chart GUI (right click the chart, Strategies, add it, pick the account).
2. Set `IsEnabled = true` inside the strategy's `State.SetDefaults` in its source, so it auto enables the next time its workspace loads, this is the only automatable substitute NinjaTrader itself supports.

`macro.develop_strategy` already does the honest thing here on its own, it writes, compiles, opens the chart, screenshots, then reports `attach_required_manual: true` with the same remediation text instead of pretending the strategy is live. Confirm real attach state with `strategy.list_running` or `strategy.state`, never assume from a macro's `ok: true` that a strategy is actually running, `ok` there only covers the automatable steps.

---

## Search and read existing code

```powershell
& $api -Command "code.search" -ArgsJson '{"query": "EnterLong"}'
& $api -Command "code.search" -ArgsJson '{"query": "CrossAbove", "type": "strategy"}'
& $api -Command "code.read" -ArgsJson '{"name": "SmaCrossover", "type": "strategy"}'
& $api -Command "code.list" -ArgsJson '{"type": "strategy"}'
```

---

## Place a trade (sim account only)

```powershell
& $api -Command "trade.place" -ArgsJson '{
  "account": "Sim101",
  "instrument": "ES 12-25",
  "action": "BUY",
  "qty": 1,
  "order_type": "MARKET"
}'

& $api -Command "position.get" -ArgsJson '{"instrument": "ES 12-25", "account": "Sim101"}'
& $api -Command "trade.close_position" -ArgsJson '{"account": "Sim101", "instrument": "ES 12-25"}'
```

Never use a non-Sim account, and never place a live order, unless the user asks for it explicitly in that exact turn. ATI must be enabled in NT8 options or these OIF file writes are silently ignored by NT8.

---

## Read logs

```powershell
& $api -Command "logs.output"
& $api -Command "logs.journal" -ArgsJson '{"lines": 100}'
& $api -Command "logs.trace" -ArgsJson '{"lines": 50, "contains": "error"}'
```

---

## Check health and live capabilities before starting work

```powershell
& $api -Command "bridge.status"
& $api -Command "system.capabilities"
```

`system.capabilities` is the authoritative live answer to "will this command work right now", it returns every catalog command tagged `working`/`best_effort`/`platform_gap` plus current backend health, prefer it over guessing from this document alone since backend availability changes with whether NT8 and the bridge are actually up. If `bridge.status`/`system.capabilities` shows the addon backend unavailable right after a fresh `bin\deploy_addon.ps1` and first compile, this is expected, NT8 only instantiates AddOn classes at startup, restart NT8 once and the bridge listener comes up on its own. The code, compile, tester, terminal, logs, and trade command families do not need the bridge at all.
