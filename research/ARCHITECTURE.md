# NinjaTrader 8 API Skill, Architecture Plan

## Purpose

A Claude Code skill that gives AI full programmatic control over NinjaTrader 8 for a **development workflow**: writing NinjaScript C# code (strategies, indicators, AddOns), compiling, deploying to charts, running backtests, capturing screenshots, reading logs, and iterating, the same workflow the MT5 skill provides for MetaTrader 5.

---

## Key Constraints Discovered in Research

| Capability | MT5 | NT8 | Impact |
|---|---|---|---|
| CLI compiler | `metaeditor64.exe /compile:` | **None**, compile only via NinjaScript Editor GUI | Must simulate F5 keypress or use external `csc.exe` |
| Open chart programmatically | Bridge EA `ChartOpen()` | **No public API** | Must use keyboard shortcut `Ctrl+Shift+N` or workspace XML manipulation |
| Change chart symbol/timeframe | Bridge EA `ChartSetSymbolPeriod()` | **ChartControl.BarsPeriod is read-only** | Must type in chart: `symbol` + Enter, or `period` + Enter |
| Add indicator to chart | Template injection | **Reflection hack only** (`ChartControl.Indicators.Add` + private `RefreshIndicators`) | Use reflection (fragile) or template manipulation |
| Run backtest | Terminal launch with `[Tester]` INI | **No Strategy Analyzer API**, GUI only | Must automate GUI via keyboard (Ctrl+R to open, then navigate) |
| File-based IPC | EA reads `Terminal/Common/Files/` | AddOn can use any filesystem path | Use `Documents\NinjaTrader 8\` or custom folder |
| HTTP server inside platform | Not possible in MQL5 | **`HttpListener` works in .NET 4.8 AddOn** | Major advantage over MT5, direct HTTP instead of file polling |
| Screenshot | Win32 `PrintWindow` (external) | `chart.GetScreenshot()` (internal, better) | Built-in chart capture from AddOn |
| Process name | `terminal64.exe` | `NinjaTrader.exe` | Different process detection |
| User data path | `%APPDATA%\MetaQuotes\Terminal\{hash}\` | `Documents\NinjaTrader 8\` | Simpler, predictable path |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Claude Code (AI Agent)                        │
│                                                                 │
│  Uses: nt8_command_api.ps1 (PowerShell CLI wrapper)             │
│        or HTTP calls to localhost:8088                           │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTP POST /v1/nt8/command
                       │ {"command": "...", "args": {...}}
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│              Python Control Plane (server.py)                    │
│              localhost:8088, ThreadingHTTPServer                │
│                                                                 │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │
│  │ Command  │  │Lifecycle │  │Idempotency│ │ Evidence       │  │
│  │ Router   │  │ Store    │  │ Store     │ │ Store          │  │
│  │          │  │ (SQLite) │  │ (SQLite)  │ │ (JSON files)   │  │
│  └────┬─────┘  └──────────┘  └──────────┘  └────────────────┘  │
│       │                                                         │
│       │ Routes to 5 backends:                                   │
│       ▼                                                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Backend Router                                           │   │
│  │                                                          │   │
│  │  1. addon_http  → HTTP to NT8 AddOn (localhost:8089)     │   │
│  │  2. file_write  → Write .cs files to bin\Custom\         │   │
│  │  3. dll_ati     → NinjaTrader.Client.dll (TCP:36973)     │   │
│  │  4. win32       → Screenshots, window management         │   │
│  │  5. keyboard    → SendKeys for compilation, chart nav    │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌──────────────┐ ┌──────────┐ ┌──────────────┐
│ NT8 AddOn    │ │ DLL ATI  │ │ Win32 / Keys │
│ (C# inside   │ │ TCP:36973│ │ pywin32      │
│  NinjaTrader) │ │          │ │ pyautogui    │
│              │ │ 28 funcs │ │              │
│ HttpListener │ │ Orders   │ │ Screenshots  │
│ localhost:   │ │ Positions│ │ Focus window │
│ 8089         │ │ Market   │ │ Send hotkeys │
│              │ │ Data     │ │ Compile (F5) │
│ Full API:    │ │          │ │              │
│ - Charts     │ └──────────┘ └──────────────┘
│ - Indicators │
│ - Screenshots│
│ - Accounts   │
│ - Market Data│
│ - Strategies │
│ - Logs       │
└──────────────┘
```

---

## 5 Backends

### 1. `addon_http`, NT8 AddOn with Embedded HTTP Server

**What:** A NinjaScript AddOn (.cs) installed in NinjaTrader that runs an `HttpListener` on `localhost:8089`. The Python control plane sends JSON commands to it.

**Handles:**
- Chart enumeration (`chart.list`)
- Indicator listing (`chart.indicator_list`)
- Account/position/order queries
- Market data subscriptions
- Screenshot capture via `chart.GetScreenshot()`
- Strategy state inspection
- Connection status
- Log reading (NinjaScript Output)

**Why needed:** Only code running inside NT8 can access the full NinjaScript API (ChartControl, Account, MarketData, etc.)

**Implementation:**
```csharp
// AntigravityBridgeAddOn.cs, placed in Documents\NinjaTrader 8\bin\Custom\AddOns\
[Gui.AddOn]
public class AntigravityBridge : AddOnBase
{
    private HttpListener _listener;
    private Thread _serverThread;
    
    protected override void OnWindowCreated(Window window)
    {
        if (window is NinjaTrader.Gui.ControlCenter)
            StartHttpServer();
    }
    
    private void StartHttpServer()
    {
        _listener = new HttpListener();
        _listener.Prefixes.Add("http://localhost:8089/");
        _listener.Start();
        _serverThread = new Thread(ListenLoop) { IsBackground = true };
        _serverThread.Start();
    }
    
    private void ListenLoop()
    {
        while (_listener.IsListening)
        {
            var ctx = _listener.GetContext();
            ThreadPool.QueueUserWorkItem(_ => HandleRequest(ctx));
        }
    }
    
    private void HandleRequest(HttpListenerContext ctx)
    {
        // Parse JSON command
        // Route to handler
        // Marshal UI ops via Dispatcher.InvokeAsync()
        // Return JSON response
    }
}
```

### 2. `file_write`, Direct File System Operations

**What:** Write/read NinjaScript .cs source files, templates, workspace XML.

**Handles:**
- `code.write_strategy`, Write .cs file to `bin\Custom\Strategies\`
- `code.write_indicator`, Write .cs file to `bin\Custom\Indicators\`
- `code.write_addon`, Write .cs file to `bin\Custom\AddOns\`
- `code.read`, Read existing .cs files
- `code.list`, List all custom scripts
- `template.read`, Read chart template XML
- `template.write`, Write chart template XML
- `workspace.read`, Read workspace XML
- `workspace.write`, Write/modify workspace XML

**Why needed:** Claude's primary job is writing code. These are simple file I/O operations.

**Key paths:**
```
Documents\NinjaTrader 8\bin\Custom\Strategies\    → Strategy .cs files
Documents\NinjaTrader 8\bin\Custom\Indicators\    → Indicator .cs files
Documents\NinjaTrader 8\bin\Custom\AddOns\        → AddOn .cs files
Documents\NinjaTrader 8\bin\Custom\DrawingTools\  → DrawingTool .cs files
Documents\NinjaTrader 8\templates\Chart\          → Chart template XML files
Documents\NinjaTrader 8\templates\Indicator\      → Indicator template XML files
Documents\NinjaTrader 8\workspaces\               → Workspace XML files
```

### 3. `dll_ati`, NinjaTrader.Client.dll (TCP ATI)

**What:** Use the 28-function DLL interface for trading operations via TCP to localhost:36973.

**Handles:**
- `trade.place`, Place orders (MARKET, LIMIT, STOPMARKET, STOPLIMIT)
- `trade.cancel`, Cancel orders
- `trade.close_position`, Close position
- `trade.flatten_all`, Flatten everything
- `trade.reverse`, Reverse position
- `market_data.subscribe`, Subscribe to L1 data
- `market_data.get`, Get last/bid/ask price
- `account.buying_power`, Account buying power
- `account.cash_value`, Account cash value
- `account.realized_pnl`, Realized P&L
- `position.get`, Current position
- `order.status`, Order status
- `order.list`, List orders
- `strategy.list`, List ATM strategies

**Why needed:** Pre-built, reliable, no AddOn required. Works for all trading operations. Polling-based (no callbacks).

**Implementation:** Python wrapper using `ctypes` or `pythonnet` to load the managed DLL.

### 4. `win32`, Window Management & Screenshots

**What:** Win32 API calls for NT8 window management and fallback screenshots.

**Handles:**
- `terminal.capture`, Background-safe screenshot via PrintWindow
- `terminal.focus`, Bring NT8 to foreground
- `terminal.arrange`, Move/resize NT8 window
- `terminal.window_state`, Minimize/maximize/restore
- `terminal.detect`, Check if NT8 is running

**Why needed:** External window management. Also fallback if AddOn screenshot fails (e.g., SharpDX rendering issues with PrintWindow).

**Implementation:** `pywin32` (`ctypes.windll.user32`), same as MT5 skill.

### 5. `keyboard`, Simulated Keyboard Input

**What:** Send keyboard shortcuts to NT8 for operations that have NO API.

**Handles:**
- `compile.trigger`, Focus NinjaScript Editor + send F5 (compile all)
- `chart.open_new`, Send Ctrl+Shift+N (New Chart dialog)
- `chart.switch_instrument`, Type symbol name + Enter in chart
- `chart.switch_timeframe`, Type period value + Enter in chart
- `tester.open`, Send Ctrl+R (open Strategy Analyzer) or right-click chart
- `tester.configure`, Navigate Strategy Analyzer UI via Tab/Enter/Arrow keys
- `editor.open`, Focus NinjaScript Editor window
- `hotkey.send`, Send arbitrary hotkey combo

**Why needed:** NT8 has NO API for compilation, chart opening, or Strategy Analyzer. Keyboard simulation is the only path for these critical dev workflow steps.

**Implementation:** `pyautogui` or `win32api.SendMessage`/`PostMessage`. Since NT8 is WPF, must target correct HwndWrapper handles.

**Key shortcuts:**
| Shortcut | Action |
|---|---|
| Ctrl+Shift+N | New Chart |
| Ctrl+R | Open Strategy Analyzer |
| F5 | Compile (in NinjaScript Editor) |
| F4 | Open MetaEditor equivalent (NinjaScript Editor from chart) |
| Ctrl+W | Close active chart |
| Ctrl+E | Toggle Expert Advisors (AutoTrading) |

---

## Command Catalog (Target)

### Code Family (file_write backend)
| Command | Required Args | Description |
|---|---|---|
| `code.write_strategy` | `name`, `content` | Write strategy .cs file |
| `code.write_indicator` | `name`, `content` | Write indicator .cs file |
| `code.write_addon` | `name`, `content` | Write AddOn .cs file |
| `code.read` | `name`, `type` | Read existing .cs file |
| `code.list` | `type` | List scripts (strategies/indicators/addons) |
| `code.delete` | `name`, `type` | Delete a .cs file |
| `code.search` | `query` | Search code files for pattern |

### Compile Family (keyboard backend)
| Command | Required Args | Description |
|---|---|---|
| `compile.all` | n/a | Focus NinjaScript Editor, send F5, wait for result |
| `compile.check` | n/a | Read compile output for errors |
| `compile.errors` | n/a | Parse last compilation errors |

### Chart Family (addon_http + keyboard backends)
| Command | Required Args | Description |
|---|---|---|
| `chart.list` | n/a | List all open charts (addon_http) |
| `chart.open` | `symbol` | Open new chart (keyboard: Ctrl+Shift+N → type symbol) |
| `chart.close` | `chart_id` | Close chart window |
| `chart.switch_instrument` | `symbol` | Type symbol + Enter on active chart |
| `chart.switch_timeframe` | `period` | Type period + Enter on active chart |
| `chart.indicator_list` | `chart_id` | List indicators on chart (addon_http) |
| `chart.indicator_add` | `indicator` | Add indicator via reflection or template (addon_http) |
| `chart.indicator_remove` | `indicator` | Remove indicator (addon_http) |
| `chart.screenshot` | n/a | Capture chart screenshot (addon_http → GetScreenshot) |
| `chart.template_save` | `name` | Save chart as template |
| `chart.template_apply` | `name` | Apply saved template |

### Strategy/EA Family (addon_http + keyboard backends)
| Command | Required Args | Description |
|---|---|---|
| `strategy.attach` | `strategy`, `symbol` | Apply strategy to chart |
| `strategy.detach` | `strategy` | Remove strategy from chart |
| `strategy.list_running` | n/a | List active strategies (addon_http) |
| `strategy.state` | `strategy` | Get strategy state/properties |
| `strategy.enable_autotrading` | n/a | Toggle AutoTrading (Ctrl+E) |

### Tester Family (keyboard + addon_http backends)
| Command | Required Args | Description |
|---|---|---|
| `tester.open` | n/a | Open Strategy Analyzer (keyboard) |
| `tester.configure` | `strategy`, `symbol`, `period`, `from_date`, `to_date` | Set up backtest params (keyboard navigation) |
| `tester.start` | n/a | Start backtest run (keyboard) |
| `tester.status` | n/a | Check if backtest is running |
| `tester.results` | n/a | Read backtest results (screenshot + parse) |

### Trade Family (dll_ati backend)
| Command | Required Args | Description |
|---|---|---|
| `trade.place` | `account`, `instrument`, `action`, `qty`, `order_type` | Place order via ATI |
| `trade.cancel` | `order_id` | Cancel order |
| `trade.close_position` | `account`, `instrument` | Close position |
| `trade.flatten_all` | n/a | Flatten everything |
| `trade.reverse` | `account`, `instrument`, `action`, `qty` | Reverse position |

### Account/Market Family (dll_ati + addon_http backends)
| Command | Required Args | Description |
|---|---|---|
| `account.info` | `account` | Buying power, cash value, P&L |
| `account.list` | n/a | List all accounts |
| `position.get` | `instrument`, `account` | Current position |
| `position.list` | n/a | All positions (addon_http) |
| `order.list` | `account` | Active orders |
| `order.status` | `order_id` | Order state |
| `market_data.subscribe` | `instrument` | Subscribe to L1 data |
| `market_data.get` | `instrument` | Get last/bid/ask |
| `market_data.history` | `instrument`, `period`, `bars_back` | Historical bars (addon_http) |

### Terminal Family (win32 + keyboard backends)
| Command | Required Args | Description |
|---|---|---|
| `terminal.detect` | n/a | Check if NT8 is running |
| `terminal.launch` | n/a | Start NinjaTrader.exe |
| `terminal.kill` | n/a | Kill NT8 process |
| `terminal.focus` | n/a | Bring NT8 to foreground |
| `terminal.capture` | n/a | Full window screenshot (win32) |
| `terminal.arrange` | `monitor_index` | Move to monitor |

### Logs Family (file_write + addon_http backends)
| Command | Required Args | Description |
|---|---|---|
| `logs.output` | n/a | Read NinjaScript Output window content |
| `logs.journal` | `lines` | Read terminal log files |
| `logs.trace` | `lines` | Read trace log files |

### Bridge Family (addon_http backend)
| Command | Required Args | Description |
|---|---|---|
| `bridge.status` | n/a | Check AddOn health + connectivity |
| `bridge.deploy` | n/a | Copy AddOn .cs to bin\Custom\AddOns, trigger compile |

### Macro Family (composite commands)
| Command | Description |
|---|---|
| `macro.develop_indicator` | Write .cs → compile → open chart → attach indicator → screenshot → return results |
| `macro.develop_strategy` | Write .cs → compile → attach to chart → verify running → screenshot |
| `macro.compile_and_test` | Compile all → open Strategy Analyzer → configure → run backtest → capture results |
| `macro.iterate_strategy` | Modify .cs → recompile → re-run backtest → compare results |
| `macro.chart_open_robust` | Detect running → focus → Ctrl+Shift+N → type symbol → wait → verify |

---

## Macro System, Development Workflow Macros

### macro.develop_indicator
```
Steps:
1. code.write_indicator(name, content)                   [file_write]
2. compile.all()                                          [keyboard]
3. compile.check(), wait for success                    [keyboard + file]
4. chart.open(symbol) OR chart.switch_instrument(symbol)  [keyboard]
5. chart.indicator_add(name)                              [addon_http]
6. chart.screenshot(name="indicator_verify")              [addon_http]
7. Return: {success, compile_errors, screenshot_path}
```

### macro.develop_strategy
```
Steps:
1. code.write_strategy(name, content)                    [file_write]
2. compile.all()                                          [keyboard]
3. compile.check(), wait for success                    [keyboard + file]
4. chart.open(symbol, period)                             [keyboard]
5. strategy.attach(name, chart_id)                        [addon_http]
6. strategy.enable_autotrading()                          [keyboard: Ctrl+E]
7. terminal.capture(name="strategy_verify")               [win32]
8. Return: {success, compile_errors, screenshot_path}
```

### macro.compile_and_test
```
Steps:
1. compile.all()                                          [keyboard]
2. compile.check(), if errors, return immediately       [file]
3. tester.open()                                          [keyboard: Ctrl+R]
4. tester.configure(strategy, symbol, period, dates)      [keyboard: Tab/Enter]
5. tester.start()                                         [keyboard]
6. tester.status(), poll until complete                  [addon_http + screenshot]
7. tester.results()                                       [screenshot + parse]
8. Return: {success, performance_metrics, screenshot_path}
```

### macro.iterate_strategy
```
Steps:
1. code.read(name, "strategy"), read current code       [file_write]
2. code.write_strategy(name, modified_content)            [file_write]
3. macro.compile_and_test(strategy, symbol, period)       [composite]
4. Return: {success, before_metrics, after_metrics, diff}
```

---

## File Structure

```
~/.claude/skills/nt8-api-control/
├── SKILL.md                          # Skill prompt (Claude reads this)
├── docs/
│   ├── SKILL_CONTRACT.md             # Triggers, rules, safety
│   ├── API_INTERNALS.md              # How the system works
│   ├── OPERATIONS_QUICKSTART.md      # Getting started
│   ├── RECIPES.md                    # Copy-paste snippets
│   ├── GOTCHAS.md                    # Known pitfalls
│   └── NINJASCRIPT_REFERENCE.md      # Quick NinjaScript API ref
├── bin/
│   ├── start_nt8_api_server.ps1      # Launch Python server
│   ├── nt8_command_api.ps1           # CLI command wrapper
│   └── deploy_addon.ps1             # Deploy bridge AddOn to NT8
├── runtime/
│   ├── server.py                     # HTTP API server (port 8088)
│   ├── controller.py                 # Command router + handlers
│   ├── backends/
│   │   ├── addon_http.py             # HTTP client to NT8 AddOn
│   │   ├── file_write.py             # .cs file I/O
│   │   ├── dll_ati.py                # NinjaTrader.Client.dll wrapper
│   │   ├── win32_capture.py          # Screenshots + window mgmt
│   │   └── keyboard.py               # Simulated keyboard input
│   ├── contracts.py                  # Types, error codes, envelope
│   ├── lifecycle.py                  # SQLite command state machine
│   ├── idempotency.py                # Request dedup
│   ├── evidence.py                   # Audit trail
│   ├── visual.py                     # Visual assertion engine
│   ├── shortcuts.py                  # NT8 hotkey catalog
│   ├── assets/
│   │   └── nt8/
│   │       └── AntigravityBridgeAddOn.cs  # The NT8 AddOn source
│   ├── tests/
│   │   ├── test_server.py
│   │   ├── test_controller.py
│   │   └── test_backends.py
│   └── captures/                     # Screenshot storage
├── references/
│   └── nt8_api_onefile.md            # Consolidated API reference
└── logs/
    ├── nt8_api_server_stdout.log
    └── nt8_api_server_stderr.log
```

---

## HTTP API Endpoints (Python Server, port 8088)

| Method | Path | Description |
|---|---|---|
| GET | `/v1/nt8/health` | Health check (NT8 process, AddOn, DLL connectivity) |
| GET | `/v1/nt8/catalog` | Full command catalog |
| GET | `/v1/nt8/shortcuts` | NT8 hotkey reference |
| GET | `/v1/nt8/metrics` | Command success/failure rates |
| GET | `/v1/nt8/errors` | Recent error log |
| GET | `/v1/nt8/evidence` | Evidence/audit trail |
| POST | `/v1/nt8/command` | Execute single command |
| POST | `/v1/nt8/command/batch` | Execute command batch |

---

## NT8 AddOn HTTP Endpoints (C# inside NT8, port 8089)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | AddOn alive check |
| GET | `/charts` | List all open charts with indicators |
| GET | `/chart/{id}/screenshot` | Capture chart screenshot, return PNG |
| GET | `/chart/{id}/indicators` | List indicators on chart |
| POST | `/chart/{id}/indicator/add` | Add indicator (reflection) |
| POST | `/chart/{id}/indicator/remove` | Remove indicator |
| GET | `/accounts` | List accounts |
| GET | `/account/{name}/state` | Account balance/equity/positions |
| GET | `/positions` | All positions |
| GET | `/orders` | All orders |
| POST | `/market-data/subscribe` | Subscribe to instrument |
| GET | `/market-data/{instrument}` | Get current quote |
| POST | `/market-data/history` | Historical bars via BarsRequest |
| GET | `/strategies` | List running strategies |
| GET | `/connections` | Connection status |
| GET | `/logs/output` | NinjaScript Output window content |

---

## Safety Rules

1. **Demo account by default**, all testing on Sim/Demo accounts
2. **No live trades without explicit confirmation**, trade guard checks account type
3. **Compile before deploy**, never attach uncompiled code
4. **Screenshot verification**, visual confirmation after every indicator/strategy attach
5. **Backup before overwrite**, save .cs.bak before modifying existing files
6. **Circuit breaker**, stop retrying after 3 identical failures

---

## Build Order (Implementation Phases)

### Phase 1: Foundation (file_write + win32 + keyboard)
- Python server skeleton (server.py, controller.py, contracts.py)
- file_write backend: code.write_*, code.read, code.list
- win32 backend: terminal.detect, terminal.launch, terminal.capture, terminal.focus
- keyboard backend: compile.all, compile.check
- Macros: None yet, test individual commands
- **Milestone:** Claude can write .cs files, compile them, and take screenshots

### Phase 2: AddOn Bridge (addon_http)
- Build AntigravityBridgeAddOn.cs
- Deploy script (deploy_addon.ps1)
- addon_http backend: chart.list, chart.indicator_list, chart.screenshot
- Account/position/order queries from AddOn
- Market data subscription
- **Milestone:** Full visibility into NT8 state from Claude

### Phase 3: Chart Operations (keyboard + addon_http)
- chart.open (Ctrl+Shift+N + type symbol)
- chart.switch_instrument, chart.switch_timeframe
- chart.indicator_add (reflection in AddOn)
- chart.indicator_remove
- strategy.attach, strategy.detach
- **Milestone:** Claude can open charts and attach scripts

### Phase 4: Strategy Tester (keyboard)
- tester.open, tester.configure, tester.start
- tester.status (screenshot-based progress detection)
- tester.results (screenshot + parse)
- **Milestone:** Claude can run backtests

### Phase 5: Trading (dll_ati)
- DLL wrapper for NinjaTrader.Client.dll
- trade.place, trade.cancel, trade.close_position, trade.flatten_all
- market_data via DLL
- **Milestone:** Claude can place trades (demo)

### Phase 6: Macros & Polish
- macro.develop_indicator
- macro.develop_strategy
- macro.compile_and_test
- macro.iterate_strategy
- Lifecycle tracking, idempotency, evidence system
- SKILL.md prompt, RECIPES.md, GOTCHAS.md
- **Milestone:** Full development workflow automation

---

## Key Differences from MT5 Skill

| Aspect | MT5 Skill | NT8 Skill |
|---|---|---|
| Bridge transport | File-based JSON queue (300ms polling) | HTTP (instant response) |
| Bridge language | MQL5 Expert Advisor | C# NinjaScript AddOn |
| Compilation | CLI (`metaeditor64.exe /compile:`) | Keyboard simulation (F5) |
| Chart operations | Full API via bridge | Keyboard simulation + limited AddOn API |
| Backtest automation | Terminal INI config launch | Keyboard automation of GUI |
| Number of backends | 5 (python, bridge_file, command_file, startup, win32) | 5 (addon_http, file_write, dll_ati, win32, keyboard) |
| Primary advantage | Full MQL5 runtime access via bridge | Full .NET API access via AddOn + HTTP |
| Primary limitation | File polling latency (~300ms) | No chart/tester programmatic APIs |
