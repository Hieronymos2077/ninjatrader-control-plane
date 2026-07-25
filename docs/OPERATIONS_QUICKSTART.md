# Operations Quickstart

Bootstrap the NT8 API skill from scratch on this machine. Project root is `C:\path\to\ninjatrader-control-plane`, every path below is relative to it unless stated otherwise.

## Prerequisites

- NinjaTrader 8.1 installed at the default path, `C:\Program Files\NinjaTrader 8\bin\NinjaTrader.exe`.
- NT8 launched at least once and logged in by a human. The Welcome/login dialog blocks every automated command until someone logs in, either typed username and password or Sign in with Google / Sign in with Apple, there is no stored password and no way to script past it on this account. After login, click through any Auto Rollover Notification dialog (Done, then a possible Rollover Yes/No confirm) or other startup dialog too, automation waits behind those exactly like the login dialog.
- PowerShell 5.1 or later (ships with Windows).
- The project venv already exists at `.venv\` (Python 3.14, created from the project root with `py -m venv .venv`). You do not need to create it again and you do not need to install anything into it. The runtime imports only the Python standard library, `ctypes`, `http.server`, `urllib`, `xml.etree.ElementTree`, `sqlite3`, plus one optional third party package, Pillow, used only to encode PNG screenshots (falls back to raw BMP output if Pillow is absent). There is no `pywin32`, no `pyautogui`, no `pythonnet`, no `requests` anywhere in `runtime\`, do not install them.

## Step 1: Deploy the bridge AddOn to NT8

```powershell
& "C:\path\to\ninjatrader-control-plane\bin\deploy_addon.ps1"
```

This copies `runtime\assets\nt8\AntigravityBridgeAddOn.cs` into `Documents\NinjaTrader 8\bin\Custom\AddOns\AntigravityBridgeAddOn.cs`, backing up any existing copy first, then verifies the copy by SHA256 hash.

## Step 2: Compile once, by hand, inside NT8

The deploy script only copies the source file, NT8 has not built it yet.

1. In NinjaTrader 8, open the Control Center menu, choose New, then NinjaScript Editor.
2. Inside the NinjaScript Editor, open any script in a tab (double click it in the NinjaScript Explorer), F5 does nothing on a blank editor with no document open.
3. Press F5. This first compile of a brand new AddOn pops a modal Warning dialog, "NinjaTrader has detected new add on(s): AntigravityBridgeAddOn... Do you wish to authorize these add ons?", click Yes.
4. Confirm no errors in the compile output (`NinjaTrader.Custom.dll`'s mtime should change, a good compile takes about 3 to 4 seconds).
5. **Restart NT8.** NT8 only instantiates AddOn classes at startup, so the bridge's HTTP listener on port 8089 does not start from this first compile alone, even though the compile itself succeeded. After the restart, the listener starts automatically the next time the Control Center window opens.

After the Python server (step 4 below) is running, subsequent compiles (for example after editing strategies or indicators, which do not need a restart) can go through the API instead:

```powershell
& "C:\path\to\ninjatrader-control-plane\bin\nt8_command_api.ps1" -Command "compile.all"
```

Note that recompiling the bridge AddOn's own source again later still requires another NT8 restart before its listener updates, the restart requirement is about the AddOn class being freshly instantiated, not about compiling in general. `addon_http` backed commands fail with `error_code ERR_ADDON_TIMEOUT` (retryable) until that restart happens. Everything else, `code.*`, `compile.all`, `tester.*`, `terminal.*`, `logs.*`, `trade.*`, works without the bridge at all.

## Step 3: (Optional) Set a non-default AddOn port

Only needed if port 8089 is taken by something else. Write the desired port as plain text to:

```
Documents\NinjaTrader 8\nt8bridge_port.txt
```

The C# bridge reads this file at startup, before falling back to its default of 8089. If you change it, also pass `-AddonPort <n>` to `start_nt8_api_server.ps1` in step 4 so the Python side's `addon_http` backend points at the same port.

## Step 4: Start the Python API server

```powershell
powershell -ExecutionPolicy Bypass -File "C:\path\to\ninjatrader-control-plane\bin\start_nt8_api_server.ps1"
```

This runs `.venv\Scripts\python.exe -m runtime` from the project root (the only correct launch command, `python runtime\server.py` has no `__main__` block and exits instantly while still looking like it started). The script waits up to 15 seconds for `GET /v1/nt8/health` to answer, then reports the listening PID. Flags: `-Hidden` (no foreground console window), `-Stop` (stop the server, refuses to kill anything that is not `python.exe` from this project's own venv), `-Port <n>` (default 8088), `-AddonPort <n>` (default 8089).

Logs go to `logs\nt8_api_server.log`.

## Step 5: Health check

```powershell
& "C:\path\to\ninjatrader-control-plane\bin\nt8_command_api.ps1" -Command "bridge.status"
```

Or:

```bash
curl http://localhost:8088/v1/nt8/health
```

Real response shape:

```json
{
  "ok": true,
  "payload": {
    "nt8_running": true,
    "addon_connected": true,
    "dll_available": true,
    "backends": {
      "file_write": {"available": true},
      "addon_http": {"available": true},
      "dll_ati": {"available": true},
      "win32": {"available": true},
      "keyboard": {"available": true}
    },
    "nt8_data_dir": "C:\\Users\\<you>\\Documents\\NinjaTrader 8",
    "workspace": "C:\\path\\to\\ninjatrader-control-plane",
    "command_count": 64
  }
}
```

`addon_connected: false` means the bridge AddOn is not compiled, not running, NT8 is not open, or NT8 has not been restarted since the AddOn was first compiled (see step 2), `chart.list`, `chart.indicator_add`, `chart.screenshot`, `account.info`, `market_data.*`, and the strategy family will fail until it is fixed. `nt8_running: false` means NinjaTrader.exe is not a running process at all.

## Step 6: Live capability check

```powershell
& "C:\path\to\ninjatrader-control-plane\bin\nt8_command_api.ps1" -Command "system.capabilities"
```

Returns every command in the catalog tagged `working`, `best_effort`, or `platform_gap`, plus the same `backend_health` block as step 5. Use this instead of guessing whether a command will work right now.

## Step 7: Run your first command

```powershell
& "C:\path\to\ninjatrader-control-plane\bin\nt8_command_api.ps1" -Command "code.list"
```

Then try the full autonomous loop:

```powershell
$argsJson = @{
  name    = "TestStrategy"
  content = "using System; using System.ComponentModel.DataAnnotations; using NinjaTrader.NinjaScript; using NinjaTrader.NinjaScript.Indicators; namespace NinjaTrader.NinjaScript.Strategies { public class TestStrategy : Strategy { protected override void OnStateChange() { if (State == State.SetDefaults) { Name = `"TestStrategy`"; Calculate = Calculate.OnBarClose; BarsRequiredToTrade = 20; } } protected override void OnBarUpdate() { if (CurrentBar < BarsRequiredToTrade) return; if (CrossAbove(SMA(10), SMA(30), 1)) EnterLong(1, `"Long`"); } } } "
  symbol  = "ES 12-25"
} | ConvertTo-Json -Depth 5 -Compress

& "C:\path\to\ninjatrader-control-plane\bin\nt8_command_api.ps1" -Command "macro.full_dev_cycle" -ArgsJson $argsJson -TimeoutSec 360
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `NT8_API_PORT` | `8088` | Python API server port |
| `NT8_ADDON_PORT` | `8089` | NT8 AddOn HTTP listener port the Python `addon_http` backend targets |
| `NT8_EVIDENCE` | `on` | Set to `off`/`0`/`false`/`no` to disable writing per command evidence JSON under `captures\validation_runs\` |

`NT8_API_PORT` and `NT8_ADDON_PORT` are set by `start_nt8_api_server.ps1` for the process it launches, you do not need to export them yourself unless running `python -m runtime` directly.

## Ports

| Port | Service |
|---|---|
| 8088 | Python API server (this skill's control plane) |
| 8089 | NT8 AddOn HTTP listener (inside NinjaTrader), overridable via `Documents\NinjaTrader 8\nt8bridge_port.txt` |
| 36973 | NT8 ATI TCP interface, used by the OIF file mechanism, not directly dialed by this skill |

## Installing the skill for Claude Code

```powershell
& "C:\path\to\ninjatrader-control-plane\bin\install_skill.ps1"
```

Copies `SKILL.md`, `docs\`, and `bin\` into `%USERPROFILE%\.claude\skills\nt8-api-control\`. The `runtime\` package is never copied there, the installed copy only points back at this project root, the actual server always runs from here.
