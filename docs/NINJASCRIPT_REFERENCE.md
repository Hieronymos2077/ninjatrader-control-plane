# NinjaScript Quick Reference

Quick reference for writing NinjaScript C# code. Covers strategies, indicators, lifecycle, orders, and common patterns.

---

## Strategy Skeleton

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
        private SMA _fastSma;
        private SMA _slowSma;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = @"Strategy description";
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
                BarsRequiredToTrade = 50;
                IsInstantiatedOnEachOptimizationIteration = true;

                FastPeriod = 10;
                SlowPeriod = 30;
            }
            else if (State == State.Configure)
            {
                // AddDataSeries("ES 06-25", BarsPeriodType.Minute, 15);
            }
            else if (State == State.DataLoaded)
            {
                _fastSma = SMA(FastPeriod);
                _slowSma = SMA(SlowPeriod);
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < BarsRequiredToTrade)
                return;

            if (CrossAbove(_fastSma, _slowSma, 1))
                EnterLong(1, "GoLong");

            if (CrossBelow(_fastSma, _slowSma, 1))
                EnterShort(1, "GoShort");
        }

        protected override void OnExecutionUpdate(Execution execution, string executionId,
            double price, int quantity, MarketPosition marketPosition,
            string orderId, DateTime time)
        {
            // Called when an order fills
        }

        protected override void OnOrderUpdate(Order order, double limitPrice,
            double stopPrice, int quantity, int filled,
            double averageFillPrice, OrderState orderState, DateTime time,
            ErrorCode error, string comment)
        {
            // Called when order state changes
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Fast Period", Order = 1, GroupName = "Parameters")]
        public int FastPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Slow Period", Order = 2, GroupName = "Parameters")]
        public int SlowPeriod { get; set; }
        #endregion
    }
}
```

---

## Indicator Skeleton with Plots

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
                Description = @"Indicator description";
                Name = "MyIndicator";
                Calculate = Calculate.OnBarClose;
                IsOverlay = false;              // false = own panel, true = on price panel
                DisplayInDataBox = true;
                DrawOnPricePanel = false;
                ScaleJustification = ScaleJustification.Right;
                IsSuspendedWhileInactive = true;

                Period = 14;

                AddPlot(Brushes.DodgerBlue, "MainPlot");
                AddPlot(new Stroke(Brushes.Red, 2), PlotStyle.Line, "SignalPlot");
                AddLine(Brushes.DarkGray, 70, "UpperLevel");
                AddLine(Brushes.DarkGray, 30, "LowerLevel");
            }
            else if (State == State.Configure)
            {
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < Period)
                return;

            MainPlot[0] = SMA(Period)[0];
            SignalPlot[0] = EMA(Period)[0];
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

        [Browsable(false)]
        [XmlIgnore]
        public Series<double> SignalPlot
        {
            get { return Values[1]; }
        }
        #endregion
    }
}
```

---

## OnStateChange Lifecycle

| State | When | Safe To Do |
|---|---|---|
| `SetDefaults` | First call, even in property grid | Set Name, Description, default values. Add plots/lines. |
| `Configure` | After user clicks OK/Apply | AddDataSeries(), set up relationships |
| `Active` | Script is running | -- |
| `DataLoaded` | Bars loaded, ready to process | Cache indicator references (e.g., `_sma = SMA(14)`) |
| `Historical` | Processing historical bars | Full bar data available |
| `Transition` | Between historical and realtime | -- |
| `Realtime` | Live data flowing | Live ticks arriving |
| `Terminated` | Script removed/stopped | Dispose resources, unsubscribe events |

**Critical**: Do NOT reference `Bars`, `Close`, `High`, etc. in `SetDefaults` or `Configure`. They are null until `DataLoaded`.

---

## Namespace Conventions

| Script Type | Namespace | File Location |
|---|---|---|
| Strategy | `NinjaTrader.NinjaScript.Strategies` | `bin\Custom\Strategies\` |
| Indicator | `NinjaTrader.NinjaScript.Indicators` | `bin\Custom\Indicators\` |
| AddOn | `NinjaTrader.NinjaScript.AddOns` | `bin\Custom\AddOns\` |
| DrawingTool | `NinjaTrader.NinjaScript.DrawingTools` | `bin\Custom\DrawingTools\` |

Class name MUST match file name (without .cs extension).

---

## Order Entry Methods

### Market Orders
```csharp
EnterLong();                                    // 1 contract, default signal
EnterLong(int quantity, string signalName);
EnterShort(int quantity, string signalName);
```

### Limit Orders
```csharp
EnterLongLimit(int quantity, double limitPrice, string signalName);
EnterShortLimit(int quantity, double limitPrice, string signalName);
```

### Stop Orders
```csharp
EnterLongStopMarket(int quantity, double stopPrice, string signalName);
EnterShortStopMarket(int quantity, double stopPrice, string signalName);
EnterLongStopLimit(int quantity, double limitPrice, double stopPrice, string signalName);
```

### Exit Orders
```csharp
ExitLong();
ExitLong(string signalName, string fromEntrySignal);
ExitShort(string signalName, string fromEntrySignal);
ExitLongLimit(int quantity, double limitPrice, string signalName, string fromEntrySignal);
ExitLongStopMarket(int quantity, double stopPrice, string signalName, string fromEntrySignal);
```

### Managed Stop/Target
```csharp
SetStopLoss(CalculationMode.Ticks, 20);
SetStopLoss("GoLong", CalculationMode.Price, Low[0] - 2 * TickSize, false);
SetProfitTarget(CalculationMode.Ticks, 40);
SetProfitTarget("GoLong", CalculationMode.Price, High[0] + 50 * TickSize);
SetTrailStop(CalculationMode.Ticks, 15);
```

---

## Built-in Indicators

### Trend
```csharp
SMA(int period)[barsAgo]                    // Simple Moving Average
EMA(int period)[barsAgo]                    // Exponential Moving Average
WMA(int period)[barsAgo]                    // Weighted Moving Average
DEMA(int period)[barsAgo]                   // Double Exponential MA
TEMA(int period)[barsAgo]                   // Triple Exponential MA
HMA(int period)[barsAgo]                    // Hull Moving Average
KAMA(int period)[barsAgo]                   // Kaufman Adaptive MA
LinReg(int period)[barsAgo]                 // Linear Regression value
LinRegIntercept(int period)[barsAgo]        // Linear Regression intercept
LinRegSlope(int period)[barsAgo]            // Linear Regression slope
```

### Momentum / Oscillators
```csharp
RSI(int period, int smooth)[barsAgo]        // Relative Strength Index
MACD(int fast, int slow, int smooth)        // MACD
    .Default[barsAgo]                       //   MACD line
    .Avg[barsAgo]                           //   Signal line
    .Diff[barsAgo]                          //   Histogram
CCI(int period)[barsAgo]                    // Commodity Channel Index
ADX(int period)[barsAgo]                    // Average Directional Index
DM(int period).DiPlus[barsAgo]              // +DI
DM(int period).DiMinus[barsAgo]             // -DI
Stochastics(int periodD, int periodK, int smooth)
    .K[barsAgo]                             // %K
    .D[barsAgo]                             // %D
StochRSI(int period)[barsAgo]               // Stochastic RSI
MFI(int period)[barsAgo]                    // Money Flow Index
ROC(int period)[barsAgo]                    // Rate of Change
Momentum(int period)[barsAgo]               // Momentum
```

### Volatility
```csharp
ATR(int period)[barsAgo]                    // Average True Range
Bollinger(double numStdDev, int period)
    .Upper[barsAgo]                         // Upper band
    .Middle[barsAgo]                        // Middle band (SMA)
    .Lower[barsAgo]                         // Lower band
KeltnerChannel(double offsetMultiplier, int period)
    .Upper[barsAgo]
    .Middle[barsAgo]
    .Lower[barsAgo]
DonchianChannel(int period)
    .Upper[barsAgo]                         // Highest high
    .Lower[barsAgo]                         // Lowest low
    .Mean[barsAgo]                          // Midpoint
StdDev(int period)[barsAgo]                 // Standard Deviation
Range()[barsAgo]                            // High - Low (single bar)
```

### Volume
```csharp
VOL()[barsAgo]                              // Volume
OBV()[barsAgo]                              // On Balance Volume
VWAP()[barsAgo]                             // Volume Weighted Avg Price
VolumeProfile(/* ... */)                    // Volume Profile
```

### Price / Misc
```csharp
MIN(ISeries<double> input, int period)[barsAgo]   // Lowest value
MAX(ISeries<double> input, int period)[barsAgo]   // Highest value
SUM(ISeries<double> input, int period)[barsAgo]   // Sum
Swing(int strength)                                // Swing high/low
    .SwingHigh[barsAgo]
    .SwingLow[barsAgo]
PivotPoint(PivotRange pivotRange, HLCCalculationMode calcMode, int width)
CurrentDayOHL()
    .CurrentOpen[barsAgo]
    .CurrentHigh[barsAgo]
    .CurrentLow[barsAgo]
PriorDayOHLC()
    .PriorOpen[barsAgo]
    .PriorHigh[barsAgo]
    .PriorLow[barsAgo]
    .PriorClose[barsAgo]
```

---

## Cross Methods

```csharp
CrossAbove(ISeries<double> series1, ISeries<double> series2, int lookBackPeriod)
CrossAbove(ISeries<double> series1, double value, int lookBackPeriod)
CrossBelow(ISeries<double> series1, ISeries<double> series2, int lookBackPeriod)
CrossBelow(ISeries<double> series1, double value, int lookBackPeriod)
```

---

## Drawing Methods

```csharp
// Horizontal/Vertical lines
Draw.HorizontalLine(NinjaScriptBase owner, string tag, double price, Brush brush);
Draw.VerticalLine(NinjaScriptBase owner, string tag, DateTime time, Brush brush);

// Lines and rays
Draw.Line(NinjaScriptBase owner, string tag, int startBarsAgo, double startY, int endBarsAgo, double endY, Brush brush);
Draw.Ray(NinjaScriptBase owner, string tag, int startBarsAgo, double startY, int endBarsAgo, double endY, Brush brush);
Draw.ExtendedLine(NinjaScriptBase owner, string tag, int startBarsAgo, double startY, int endBarsAgo, double endY, Brush brush);

// Markers
Draw.ArrowUp(NinjaScriptBase owner, string tag, int barsAgo, double y, Brush brush);
Draw.ArrowDown(NinjaScriptBase owner, string tag, int barsAgo, double y, Brush brush);
Draw.Diamond(NinjaScriptBase owner, string tag, int barsAgo, double y, Brush brush);
Draw.Dot(NinjaScriptBase owner, string tag, int barsAgo, double y, Brush brush);
Draw.Square(NinjaScriptBase owner, string tag, int barsAgo, double y, Brush brush);
Draw.TriangleUp(NinjaScriptBase owner, string tag, int barsAgo, double y, Brush brush);
Draw.TriangleDown(NinjaScriptBase owner, string tag, int barsAgo, double y, Brush brush);

// Text
Draw.Text(NinjaScriptBase owner, string tag, string text, int barsAgo, double y, Brush brush);
Draw.TextFixed(NinjaScriptBase owner, string tag, string text, TextPosition textPosition);

// Shapes
Draw.Rectangle(NinjaScriptBase owner, string tag, int startBarsAgo, double startY, int endBarsAgo, double endY, Brush brush);
Draw.Region(NinjaScriptBase owner, string tag, int startBarsAgo, int endBarsAgo, ISeries<double> series1, ISeries<double> series2, Brush outlineBrush, Brush areaBrush, int areaOpacity);

// Remove
RemoveDrawObject(string tag);
```

---

## Property Attributes

```csharp
[NinjaScriptProperty]
// Required for parameter to appear in Strategy Analyzer optimization.
// Also makes it a constructor parameter for indicator calls from other scripts.

[Display(Name = "Fast Period", Description = "Lookback for fast MA",
         Order = 1, GroupName = "Parameters")]
// Controls UI display in property grid.

[Range(1, 1000)]
// Numeric validation. Works with int and double.

[Browsable(false)]
// Hides property from property grid. Use for Series<double> plot accessors.

[XmlIgnore]
// Excludes from template serialization. Always pair with [Browsable(false)] for plots.
```

---

## AddDataSeries (Multi-Timeframe / Multi-Instrument)

```csharp
// In OnStateChange, State == State.Configure:
AddDataSeries("ES 06-25", BarsPeriodType.Minute, 15);   // 15-min ES
AddDataSeries("NQ 06-25", BarsPeriodType.Minute, 5);    // 5-min NQ
AddDataSeries(BarsPeriodType.Day, 1);                    // Daily of primary

// In OnBarUpdate:
if (BarsInProgress == 0)  // Primary series
{
    // ...
}
else if (BarsInProgress == 1)  // First added series (15-min ES)
{
    // Access via: Closes[1][0], Opens[1][0], etc.
}
```

---

## Bars Period Types

| Enum | Description | Example |
|---|---|---|
| `BarsPeriodType.Minute` | Minute bars | 1, 5, 15, 30, 60 |
| `BarsPeriodType.Day` | Daily bars | 1 |
| `BarsPeriodType.Week` | Weekly bars | 1 |
| `BarsPeriodType.Month` | Monthly bars | 1 |
| `BarsPeriodType.Second` | Second bars | 10, 30 |
| `BarsPeriodType.Tick` | Tick bars | 133, 233, 500 |
| `BarsPeriodType.Volume` | Volume bars | 500, 1000, 5000 |
| `BarsPeriodType.Range` | Range bars | 2, 4, 8 |
| `BarsPeriodType.Renko` | Renko bars | 4, 8 |

---

## Common Data Access

```csharp
// Price series (primary instrument)
Open[barsAgo]       High[barsAgo]       Low[barsAgo]        Close[barsAgo]
Volume[barsAgo]     Time[barsAgo]

// Multi-series
Opens[barSeriesIndex][barsAgo]
Closes[barSeriesIndex][barsAgo]

// Bar info
CurrentBar          // Current bar index (0-based)
BarsInProgress      // Which data series is updating (0 = primary)
Count               // Total bars loaded

// Time
Time[0]             // DateTime of current bar
ToDay(Time[0])      // YYYYMMDD int
ToTime(Time[0])     // HHmmss int

// Position
Position.MarketPosition   // Flat, Long, Short
Position.Quantity
Position.AveragePrice

// Instrument
Instrument.MasterInstrument.Name
Instrument.MasterInstrument.PointValue
TickSize
```

---

## Calculate Modes

| Mode | Behavior |
|---|---|
| `Calculate.OnBarClose` | OnBarUpdate fires once per bar close. Most common. |
| `Calculate.OnEachTick` | OnBarUpdate fires on every tick. Use for scalping. |
| `Calculate.OnPriceChange` | OnBarUpdate fires when price changes (dedup ticks at same price). |

---

## Session/Time Filters

```csharp
// Only trade during regular session
if (Times[0][0].TimeOfDay < new TimeSpan(9, 30, 0)) return;
if (Times[0][0].TimeOfDay > new TimeSpan(16, 0, 0)) return;

// Check day of week
if (Time[0].DayOfWeek == DayOfWeek.Friday) return;

// Use Bars.IsFirstBarOfSession
if (Bars.IsFirstBarOfSession)
{
    // Reset daily variables
}
```
