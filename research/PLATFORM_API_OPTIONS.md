# NinjaTrader API Deep Research

## Overview: 6 API Options Compared

| # | API | Cost | Language | Transport | Best For |
|---|-----|------|----------|-----------|----------|
| 1 | **NinjaScript (Strategy/Indicator)** | Free (sim), paid (live) | C# | Internal to NT8 | Full-featured trading bots inside NT8 |
| 2 | **NinjaScript AddOn** | Free (sim), paid (live) | C# + WPF | Internal to NT8 | Building a REST/WebSocket server inside NT8 |
| 3 | **DLL API** (NinjaTrader.Client.dll) | Free | Any .NET language | TCP localhost:36973 | External apps controlling NT8 |
| 4 | **Community Wrappers** | Free | Python, Node.js, TS | DLL / Files / TCP | Quick integration from non-C# languages |
| 5 | **CrossTrade REST API** | ~$30-50/mo | Any | HTTPS + WSS cloud | Remote control of NT8 from anywhere |
| 6 | **Tradovate Broker API** | Free (needs account) | Any | HTTPS + WSS | Direct broker access without NT8 desktop |

---

## 1. NinjaScript Strategy/Indicator API

**What it is:** C# scripts that run inside NinjaTrader 8. The primary and most powerful free option.

### Function Categories

#### Market Data Access
| Function | What It Does |
|----------|-------------|
| `Open[0]`, `High[0]`, `Low[0]`, `Close[0]`, `Volume[0]`, `Time[0]` | Current bar OHLCVT data |
| `Opens[1][0]`, `Highs[1][0]`, etc. | Multi-timeframe data from added series |
| `AddDataSeries(BarsPeriodType.Day, 1)` | Add secondary timeframe or instrument |
| `BarsInProgress` | Index of which data series is currently updating |
| `OnMarketData(MarketDataEventArgs e)` | Tick-level L1 data (every bid/ask/last change) |
| `OnMarketDepth(MarketDepthEventArgs e)` | L2 order book depth updates |
| `e.Price`, `e.Volume`, `e.Time`, `e.MarketDataType` | Tick event properties |

#### Order Management (Managed Approach - simpler)
| Function | What It Does |
|----------|-------------|
| `EnterLong()` / `EnterShort()` | Market entry |
| `EnterLongLimit()` / `EnterShortLimit()` | Limit entry |
| `EnterLongStopMarket()` / `EnterShortStopMarket()` | Stop entry |
| `EnterLongStopLimit()` / `EnterShortStopLimit()` | Stop-limit entry |
| `EnterLongMIT()` / `EnterShortMIT()` | Market-if-touched entry |
| `ExitLong()` / `ExitShort()` | Market exit |
| `ExitLongLimit()` / `ExitShortLimit()` | Limit exit |
| `ExitLongStopMarket()` / `ExitShortStopMarket()` | Stop exit |
| `SetStopLoss()` | Auto stop-loss |
| `SetProfitTarget()` | Auto profit target |
| `SetTrailStop()` | Trailing stop |
| `SetParabolicStop()` | Parabolic SAR stop |
| `CancelOrder()` | Cancel specific order |

#### Order Management (Unmanaged Approach - full control)
| Function | What It Does |
|----------|-------------|
| `SubmitOrderUnmanaged()` | Direct order submission, no convenience layer |
| `ChangeOrder()` | Modify working order |
| `CancelOrder()` | Cancel order |
| `GetRealtimeOrder()` | Get live order object |

#### ATM Strategy Control
| Function | What It Does |
|----------|-------------|
| `AtmStrategyCreate()` | Create ATM strategy instance |
| `AtmStrategyCancelEntryOrder()` | Cancel pending ATM entry |
| `AtmStrategyChangeEntryOrder()` | Modify ATM entry |
| `AtmStrategyChangeStopTarget()` | Change stop/target levels |
| `AtmStrategyClose()` | Close ATM position |
| `GetAtmStrategyMarketPosition()` | Current ATM position direction |
| `GetAtmStrategyPositionQuantity()` | Current ATM position size |
| `GetAtmStrategyRealizedProfitLoss()` | ATM realized P&L |
| `GetAtmStrategyUnrealizedProfitLoss()` | ATM unrealized P&L |

#### Event Handlers
| Event | What It Does |
|-------|-------------|
| `OnBarUpdate()` | Fires on each new bar (primary logic goes here) |
| `OnMarketData()` | Fires on every L1 tick |
| `OnMarketDepth()` | Fires on L2 book changes |
| `OnOrderUpdate()` | Order state changes (filled, cancelled, rejected) |
| `OnExecutionUpdate()` | Trade executions (fills) |
| `OnPositionUpdate()` | Position changes |

#### 100+ Built-in Indicators (callable in code)
| Category | Examples |
|----------|---------|
| Moving Averages | SMA, EMA, DEMA, TEMA, HMA, KAMA, VWMA, WMA, ZLEMA |
| Momentum | RSI, MACD, Stochastics, CCI, MFI, ROC, WilliamsR, TSI |
| Trend | ADX, ParabolicSAR, BollingerBands, KeltnerChannel, DonchianChannel |
| Volume | OBV, ChaikinMoneyFlow, ADL, VolumeOscillator |
| Statistical | Correlation, StandardDeviation, ZigZag, Swing |

#### Chart Drawing
35+ drawing tools: `Draw.HorizontalLine()`, `Draw.Rectangle()`, `Draw.FibonacciRetracements()`, `Draw.Text()`, `Draw.ArrowUp()`, `Draw.TrendChannel()`, etc. Plus custom GPU rendering via SharpDX `OnRender()`.

#### Performance Metrics
| Property | What It Does |
|----------|-------------|
| `SystemPerformance.AllTrades` | Complete trade history |
| Net profit, max drawdown, Sharpe ratio, win rate, profit factor | All accessible in code |

### Uniqueness
- **Most powerful**: Full access to everything NT8 can do
- **Backtesting + optimization**: Only option that can backtest and optimize strategies
- **100+ indicators built in**: Call any indicator as a one-liner in your strategy
- **Chart drawing**: Full visual annotation capability

### Limitation
- C# only, runs inside NT8, no external access unless you build a bridge

---

## 2. NinjaScript AddOn API (Superset of #1)

**What it is:** A C# + WPF project that extends NT8 as a platform plugin. Can do everything a Strategy can PLUS platform-wide access.

### Extra Capabilities Beyond Strategies

| Capability | What It Does |
|-----------|-------------|
| `Account.All` | Access ALL accounts (not just the one a strategy runs on) |
| `Account.Get(AccountItem.CashValue)` | Query any account balance field |
| `Account.CreateOrder()`, `Submit()`, `Cancel()`, `Flatten()` | Direct order management on any account |
| `Account.OrderUpdate`, `ExecutionUpdate`, `PositionUpdate` events | Platform-wide event streams |
| `NTWindow` / `NTTabPage` | Create custom floating/dockable windows |
| `NTMenuItem` | Add items to NinjaTrader's menus |
| `IInstrumentProvider` / `IIntervalProvider` | Sync with NT8's instrument/interval linking |
| `IWorkspacePersistence` | Save/restore window state in workspaces |
| `Connection.Status`, `Connect()`, `Disconnect()` | Manage broker connections |
| Market data subscription without a chart | Subscribe to any instrument independently |

### Uniqueness
- **THE recommended path for building your own API**: Create an AddOn that spins up an HTTP server (e.g., Kestrel) inside NT8, exposing a REST API to external apps
- **Platform-wide access**: Not scoped to a single chart or strategy
- **Custom UI**: Can build full WPF windows inside NT8
- **Can bridge to anything**: Since it's C#, you can embed an HTTP server, WebSocket server, gRPC server, or TCP listener

### Limitation
- C# only, requires Visual Studio for development
- Cannot programmatically enable/disable strategies
- Cannot run backtests programmatically

---

## 3. DLL API (NinjaTrader.Client.dll / NTDirect.dll)

**What it is:** Two DLL files that ship with NT8. Any external application can load them to control NT8 over TCP (localhost:36973).

- `NinjaTrader.Client.dll`, Managed .NET DLL at `C:\Program Files\NinjaTrader 8\bin\`
- `NTDirect.dll`, Unmanaged C/C++ DLL at `C:\Windows\SysWOW64\`
- Both expose **identical functions**, just different calling conventions

### Prerequisites
- NT8 must be running
- Enable: Tools > Options > Automated Trading Interface

### Complete Function List (28 functions)

#### Connection (3 functions)
| Function | Signature | Returns | What It Does |
|----------|-----------|---------|-------------|
| `SetUp` | `(string host, int port)` | `int` (0=ok, -1=err) | Set connection target. Default: localhost:36973 |
| `Connected` | `(int showMessage)` | `int` (0=connected, -1=no) | Check if connected to NT8. showMessage=1 shows dialog |
| `TearDown` | `()` | `int` | Disconnect from NT8 |

#### Market Data (9 functions)
| Function | Signature | Returns | What It Does |
|----------|-----------|---------|-------------|
| `SubscribeMarketData` | `(string instrument)` | `int` | Start live data stream |
| `UnsubscribeMarketData` | `(string instrument)` | `int` | Stop data stream |
| `MarketData` | `(string instrument, int type)` | `double` | Get price. type: 0=Last, 1=Bid, 2=Ask |
| `Ask` | `(string instrument, double price, int size)` | `int` | Set ask (for playback/custom feeds) |
| `AskPlayback` | `(string instrument, double price, int size, string timestamp)` | `int` | Set ask with timestamp |
| `Bid` | `(string instrument, double price, int size)` | `int` | Set bid |
| `BidPlayback` | `(string instrument, double price, int size, string timestamp)` | `int` | Set bid with timestamp |
| `Last` | `(string instrument, double price, int size)` | `int` | Set last trade |
| `LastPlayback` | `(string instrument, double price, int size, string timestamp)` | `int` | Set last with timestamp |

#### Order Management (3 functions)
| Function | Signature | Returns | What It Does |
|----------|-----------|---------|-------------|
| `NewOrderId` | `()` | `string` | Generate unique order ID |
| `Command` | `(string command, string account, string instrument, string action, int quantity, string orderType, double limitPrice, double stopPrice, string timeInForce, string oco, string orderId, string strategy, string strategyId)` | `int` | **THE master function**, handles all order operations |
| `ConfirmOrders` | `(int confirm)` | `int` | Toggle order confirmation dialogs |

##### Command() valid commands:
| Command | What It Does |
|---------|-------------|
| `PLACE` | Submit new order (BUY/SELL, MARKET/LIMIT/STOPMARKET/STOPLIMIT) |
| `CANCEL` | Cancel specific order by orderId |
| `CANCELALLORDERS` | Cancel all orders across all accounts |
| `CHANGE` | Modify working order (price, quantity) |
| `CLOSEPOSITION` | Close position for instrument on account |
| `CLOSESTRATEGY` | Close ATM strategy by strategyId |
| `FLATTENEVERYTHING` | Flatten all positions + cancel all orders everywhere |
| `REVERSEPOSITION` | Flip position direction |

#### Order Status (4 functions)
| Function | Signature | Returns | What It Does |
|----------|-----------|---------|-------------|
| `OrderStatus` | `(string orderId)` | `string` | Status: Filled, Working, Cancelled, Rejected, PartFilled |
| `Filled` | `(string orderId)` | `int` | Number of contracts filled |
| `AvgFillPrice` | `(string orderId)` | `double` | Average fill price |
| `Orders` | `(string account)` | `string` | All order IDs separated by `\|` |

#### Position & Account (5 functions)
| Function | Signature | Returns | What It Does |
|----------|-----------|---------|-------------|
| `MarketPosition` | `(string instrument, string account)` | `int` | 0=flat, +N=long, -N=short |
| `AvgEntryPrice` | `(string instrument, string account)` | `double` | Average entry price |
| `RealizedPnL` | `(string account)` | `double` | Session realized P&L |
| `BuyingPower` | `(string account)` | `double` | Account buying power |
| `CashValue` | `(string account)` | `double` | Account cash value |

#### ATM Strategy (4 functions)
| Function | Signature | Returns | What It Does |
|----------|-----------|---------|-------------|
| `Strategies` | `(string account)` | `string` | All ATM strategy IDs separated by `\|` |
| `StrategyPosition` | `(string strategyId)` | `int` | ATM position: 0=flat, +/-N |
| `StopOrders` | `(string strategyId)` | `string` | Stop order IDs for ATM |
| `TargetOrders` | `(string strategyId)` | `string` | Target order IDs for ATM |

### C# Usage Example
```csharp
using NinjaTrader.Client;

var client = new Client();
client.SetUp("localhost", 36973);
int status = client.Connected(1);           // 0 = connected
client.SubscribeMarketData("ES 09-24");
double last = client.MarketData("ES 09-24", 0);  // last price
string orderId = client.NewOrderId();
client.Command("PLACE", "Sim101", "ES 09-24", "BUY", 1, "MARKET", 0, 0, "DAY", "", orderId, "", "");
client.UnsubscribeMarketData("ES 09-24");
client.TearDown();
```

### Uniqueness
- **Language-agnostic**: Any language that can load a DLL (C#, Python via pythonnet, C++, etc.)
- **Simplest external integration**: 28 functions, straightforward
- **No NT8 code changes needed**: Just enable ATI in settings

### Limitations
- **No historical data**: Only live bid/ask/last
- **No indicators**: Can't call RSI, MACD etc.
- **No chart interaction**: Can't draw or read chart objects
- **No L2 depth**: Only L1 data
- **Polling only**: No event callbacks, you must poll for status
- **Local only**: Must run on same machine as NT8

---

## 4. Community Wrappers

### 4a. miasmos/ninjatrader (TypeScript/Node.js), BEST community option for NT8

**Transport:** File-based AT Interface. Writes command `.txt` files to NT8's `incoming/` folder, reads status from `outgoing/`.

#### Functions
| Method | What It Does |
|--------|-------------|
| `market(opts)` | Place market order |
| `limit(opts)` | Place limit order |
| `stop(opts)` | Place stop order |
| `stopLimit(opts)` | Place stop-limit order |
| `marketMany(opts[])` / `limitMany()` / `stopMany()` / `stopLimitMany()` | Batch order submission |
| `cancel(opts)` | Cancel order by ID |
| `change(opts)` | Modify order (qty + stopPrice only) |
| `cancelAll()` | Cancel all orders |
| `close(opts)` | Close position |
| `closeStrategy(opts)` | Close ATM strategy |
| `flatten()` | Flatten everything |
| `reverse(opts)` | Reverse position |
| `onConnected(feedName, cb)` | Watch for data feed connection |
| `onDisconnected(feedName, cb)` | Watch for disconnection |
| `onPosition(instrument, cb)` | Position change callbacks (LONG/SHORT/FLAT, qty, price) |

**Event callbacks on each order:** `onFilled`, `onSubmitted`, `onCancelled`, `onRejected`, `onAccepted`, `onWorking`, `onPartiallyFilled`

**Uniqueness:** Event-driven callbacks (not polling). Pure TypeScript, no native binaries.
**Limitation:** No market data/prices, no account balance, ~100ms latency (file polling).

### 4b. keleko34/NTDirect32-NodeJS (Node.js)

**Transport:** Native C++ addon wrapping NtDirect.dll directly.

**Functions:** Mirrors all 28 DLL functions (see Section 3 above) with Node.js-friendly names like `placeBuyOrder()`, `placeSellOrder()`, `marketData()`, etc.

**Uniqueness:** Direct DLL access from Node.js, lowest latency of community options.
**Limitation:** **NinjaTrader 7 ONLY** (NtDirect.dll path is NT7). 32-bit Windows only. Requires node-gyp.

### 4c. TheSnowGuru/CSharpNinja-Python-NT8

**Transport:** TCP socket to MetaTrader 4/5 terminal.

**Functions:** `Connect()`, `Get_last_x_bars_from_now()`, `Get_all_orders()`, `Get_all_open_positions()`, `Get_static_account_info()`, `Get_instrument_info()`, etc.

**Uniqueness:** Gets historical bar data (not just live ticks).
**Limitation:** **Requires MT4/MT5 running alongside NT8**, NT8 is just the strategy engine, execution routes through MetaTrader. Name is misleading (no actual Python). Demo limited to 6 instruments, full version is paid.

---

## 5. CrossTrade REST API (Paid, ~$30-50/mo)

**What it is:** Cloud proxy that relays HTTP/WebSocket calls to a running NT8 desktop via an installed add-on.

**Base URL:** `https://app.crosstrade.io/v1/api/`
**WebSocket:** `wss://app.crosstrade.io/ws/stream`
**Auth:** Static Bearer token

### 25 REST Endpoints

#### Accounts (2)
| Endpoint | What It Does |
|----------|-------------|
| `GET /accounts` | List all NT8 accounts |
| `GET /accounts/{account}` | Full account detail (52 fields: buyingPower, cashValue, netLiquidation, margins, etc.) |

#### Positions (5)
| Endpoint | What It Does |
|----------|-------------|
| `GET /accounts/{account}/positions` | All open positions |
| `POST /accounts/{account}/positions/close` | Close by instrument (optional quantity or percent) |
| `POST /accounts/{account}/positions/reverse` | True reversal |
| `POST /accounts/{account}/positions/flatten` | Flatten account (optional instrument filter) |
| `POST /positions/flatten-everything` | Flatten ALL accounts ALL instruments |

#### Orders (9)
| Endpoint | What It Does |
|----------|-------------|
| `GET /orders` | All orders across all accounts |
| `GET /accounts/{account}/orders` | Orders for one account |
| `GET /accounts/{account}/orders/{orderId}` | Single order detail |
| `GET /accounts/{account}/orders/{orderId}/status` | Order status |
| `POST /accounts/{account}/orders/place` | Place order (MARKET/LIMIT/STOPMARKET/STOPLIMIT) |
| `POST /accounts/{account}/orders/flat-place` | Flatten first, then place new order |
| `POST /accounts/{account}/orders/{orderId}/cancel` | Cancel one order |
| `POST /accounts/{account}/orders/cancel` | Cancel all orders (optional instrument filter) |
| `POST /orders/cancel-all` | Cancel ALL orders ALL accounts |
| `POST /accounts/{account}/orders/{orderId}/replace` | Cancel + place replacement |
| `PUT /accounts/{account}/orders/{orderId}/change` | Modify order in-place |
| `POST /accounts/{account}/orders/cancel-and-bracket` | Cancel + add bracket (TP/SL) |

#### Strategies (3)
| Endpoint | What It Does |
|----------|-------------|
| `GET /strategies` | List active ATM strategies |
| `GET /strategies/{strategyId}` | Single ATM strategy detail |
| `POST /strategies/{strategyId}/close` | Close ATM strategy |

#### Executions (3)
| Endpoint | What It Does |
|----------|-------------|
| `GET /accounts/{account}/executions` | Execution history (max 900s lookback) |
| `GET /accounts/{account}/executions/{executionId}` | Single execution |
| `GET /accounts/{account}/executions/by-order/{orderId}` | Executions for an order |

#### Quotes (1)
| Endpoint | What It Does |
|----------|-------------|
| `GET /accounts/{account}/quote?instrument=ES 12-25` | Real-time quote (bid, ask, last, OHLC, volume, tickSize, pointValue) |

#### WebSocket Streaming
| Action | What It Does |
|--------|-------------|
| `subscribe` | Subscribe to real-time quotes (~1s intervals) |
| `unsubscribe` | Stop quote stream |
| `streamPnl` | Toggle P&L streaming |
| `rpc` | Call any REST endpoint over WebSocket |

### Rate Limits
- 3 req/sec sustained, burst of 20
- Max 1 WebSocket connection per account

### Uniqueness
- **Remote access**: Control NT8 from anywhere (phone, cloud server, another machine)
- **Any language**: Standard REST + WebSocket
- **Richest account data**: 52 account fields
- **Bracket orders**: Dedicated cancel-and-bracket endpoint

### Limitations
- Paid subscription required
- NT8 + add-on must be running
- ~1s quote conflation on WebSocket
- No historical data, no indicators, no chart access

---

## 6. Tradovate Broker API (Free with Account)

**What it is:** Direct REST + WebSocket API to Tradovate (NinjaTrader's brokerage). Bypasses NT8 desktop entirely.

**Base URL:** `https://demo.tradovateapi.com/v1` (demo) / `https://live.tradovateapi.com/v1` (live)
**Auth:** OAuth 2.0 Bearer token (1-hour expiry, must renew)

### 200+ Endpoints Across 11 Domains

#### Orders (~45 endpoints, key ones)
| Endpoint | What It Does |
|----------|-------------|
| `POST /order/placeorder` | Submit order |
| `POST /order/cancelorder` | Cancel order |
| `POST /order/modifyorder` | Modify price/qty |
| `POST /order/placeoco` | One-Cancels-Other pair |
| `POST /order/placeoso` | One-Sends-Other (bracket) |
| `GET /order/list` | All orders |

#### Positions (~12 endpoints)
| Endpoint | What It Does |
|----------|-------------|
| `GET /position/list` | All open positions |
| `GET /position/item` | Single position |
| `GET /fillPair/list` | Fill pair records |

#### Accounts (~23 endpoints)
| Endpoint | What It Does |
|----------|-------------|
| `GET /account/list` | All accounts |
| `GET /cashBalance/list` | Cash balances |
| `GET /marginSnapshot/list` | Margin snapshots |

#### Contracts (~52 endpoints)
| Endpoint | What It Does |
|----------|-------------|
| `GET /contract/find` | Find by symbol |
| `GET /contract/suggest` | Search contracts |
| `GET /product/list` | All tradeable products |
| `GET /exchange/list` | Exchanges |
| `GET /productSession/list` | Trading sessions |

#### Risk Management (~26 endpoints)
| Endpoint | What It Does |
|----------|-------------|
| `POST /userAccountAutoLiq/create` | Auto-liquidation rules |
| `POST /userAccountPositionLimit/create` | Position size limits |
| `GET /contractMargin/list` | Margin requirements |

#### Alerts (~16 endpoints)
| Endpoint | What It Does |
|----------|-------------|
| `POST /alert/create` | Price/status alerts |
| `GET /alert/list` | All alerts |
| `GET /alertSignal/list` | Triggered signals |

#### WebSocket (2 separate connections)
| Connection | What It Does |
|-----------|-------------|
| Trading WS | Order events, position updates, execution reports, account changes |
| Market Data WS | `md/subscribeQuote`, `md/subscribeDOM` (L2), `md/getChart` (historical bars), `md/subscribeHistogram` |

### Rate Limits
- 5,000 requests per 60-minute window
- Token expires every 1 hour

### Uniqueness
- **No NT8 desktop needed**: Direct broker access from any machine
- **Most endpoints**: 200+ vs 25 (CrossTrade)
- **L2 DOM data**: Order book depth via WebSocket
- **Historical chart data**: `md/getChart` endpoint
- **Risk management**: Auto-liquidation, position limits
- **Alerts system**: Server-side price alerts
- **Contract database**: Full instrument metadata

### Limitations
- **Tradovate account required** (NinjaTrader's brokerage only)
- **No NinjaScript**: No indicators, no strategies, no backtesting
- **No ATM strategies**: Tradovate doesn't support NT8's ATM concept
- **Live market data costs extra**: CME sub-vendor license ($290-500+/mo)
- **Token management**: Must renew every hour

---

## Decision Matrix: Which Approach to Build Your Custom API?

### If you want: AI controlling NT8 locally on same machine
**Best: AddOn (#2) that embeds an HTTP server**
- Build a NinjaScript AddOn in C#
- Embed a lightweight HTTP server (Kestrel / HttpListener)
- Expose REST endpoints that call NT8's internal APIs
- AI sends HTTP requests to localhost
- You get: indicators, market data, orders, positions, account info, chart drawing, everything

### If you want: Simplest possible integration, don't need indicators
**Best: DLL API (#3)**
- Load `NinjaTrader.Client.dll` from Python/Node/any language
- 28 functions, straightforward
- Enough for: place orders, check positions, get live prices

### If you want: Control NT8 from a remote machine / cloud
**Best: AddOn (#2) with tunneling, OR CrossTrade (#5) if you want plug-and-play**
- AddOn + Cloudflare tunnel = free remote REST API
- CrossTrade = paid but zero development effort

### If you want: Skip NT8 desktop entirely
**Best: Tradovate API (#6)**
- Direct broker access, 200+ endpoints
- But: no indicators, no backtesting, need Tradovate account

### If you want: Quick prototype in Python/Node without C#
**Best: miasmos/ninjatrader (#4a) for Node.js, or DLL + pythonnet for Python**
- File-based API is simple but limited (no market data)
- DLL via pythonnet gives you the full 28-function set

---

## Recommended Architecture for AI + NinjaTrader

```
                    +-----------------+
                    |   AI Agent      |
                    |  (Python/Node)  |
                    +--------+--------+
                             |
                        HTTP/WebSocket
                             |
                    +--------v--------+
                    |  NinjaScript    |
                    |  AddOn (C#)     |
                    |  + HTTP Server  |
                    +--------+--------+
                             |
                      NT8 Internal API
                             |
              +--------------+--------------+
              |              |              |
        +-----v----+  +-----v----+  +------v-----+
        | Market    |  | Order    |  | Account    |
        | Data      |  | Mgmt     |  | & Position |
        | + Indicators| | + ATM   |  | + P&L      |
        +-----------+  +----------+  +------------+
```

This gives you the best of all worlds: full NT8 power, any-language access, local or remote capable.
