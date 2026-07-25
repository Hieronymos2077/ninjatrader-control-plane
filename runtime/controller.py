from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .backends.base import BackendBase, ExecutionResult
    from .shortcuts import list_nt8_shortcuts
    from .visual import DEFAULT_ROI_REGISTRY, DEFAULT_VISUAL_REQUIREMENTS, VisualAssertionEngine
except ImportError:
    from backends.base import BackendBase, ExecutionResult
    from shortcuts import list_nt8_shortcuts
    from visual import DEFAULT_ROI_REGISTRY, DEFAULT_VISUAL_REQUIREMENTS, VisualAssertionEngine


NT8_COMMAND_CATALOG: dict[str, dict[str, Any]] = {
    # ── Code family ──────────────────────────────────────────────────────
    "code.write_strategy": {
        "required_args": ["name", "content"],
        "optional_args": [],
        "backends": ["file_write"],
        "description": "Write strategy .cs file to NinjaScript Strategies folder.",
    },
    "code.write_indicator": {
        "required_args": ["name", "content"],
        "optional_args": [],
        "backends": ["file_write"],
        "description": "Write indicator .cs file to NinjaScript Indicators folder.",
    },
    "code.write_addon": {
        "required_args": ["name", "content"],
        "optional_args": [],
        "backends": ["file_write"],
        "description": "Write AddOn .cs file to NinjaScript AddOns folder.",
    },
    "code.read": {
        "required_args": ["name", "type"],
        "optional_args": [],
        "backends": ["file_write"],
        "description": "Read a NinjaScript .cs file by name and type (strategy/indicator/addon).",
    },
    "code.list": {
        "required_args": [],
        "optional_args": ["type"],
        "backends": ["file_write"],
        "description": "List NinjaScript files, optionally filtered by type.",
    },
    "code.delete": {
        "required_args": ["name", "type"],
        "optional_args": [],
        "backends": ["file_write"],
        "description": "Delete a NinjaScript .cs file.",
    },
    "code.search": {
        "required_args": ["query"],
        "optional_args": [],
        "backends": ["file_write"],
        "description": "Search NinjaScript code files for a text pattern.",
    },

    # ── Compile family ───────────────────────────────────────────────────
    "compile.all": {
        "required_args": [],
        "optional_args": [],
        "backends": ["keyboard"],
        "description": "Compile all NinjaScript code (F5 hotkey).",
    },
    "compile.check": {
        "required_args": [],
        "optional_args": [],
        "backends": ["file_write"],
        "description": "Check compile output window for success/errors.",
    },
    "compile.errors": {
        "required_args": [],
        "optional_args": [],
        "backends": ["file_write"],
        "description": "Parse compile error log for structured error list.",
    },

    # ── Chart family ─────────────────────────────────────────────────────
    "chart.list": {
        "required_args": [],
        "optional_args": [],
        "backends": ["addon_http"],
        "description": "List open chart windows with instrument and timeframe.",
    },
    "chart.open": {
        "required_args": ["symbol"],
        "optional_args": ["period"],
        "backends": ["keyboard"],
        "description": "Open new chart window for given instrument.",
    },
    "chart.close": {
        "required_args": [],
        "optional_args": ["chart_id"],
        "backends": ["addon_http", "keyboard"],
        "description": "Close active or specified chart window.",
    },
    "chart.switch_instrument": {
        "required_args": ["symbol"],
        "optional_args": ["chart_id"],
        "backends": ["keyboard"],
        "description": "Switch active chart to a different instrument.",
    },
    "chart.switch_timeframe": {
        "required_args": ["period"],
        "optional_args": ["chart_id"],
        "backends": ["keyboard"],
        "description": "Switch active chart to a different timeframe/period.",
    },
    "chart.indicator_list": {
        "required_args": [],
        "optional_args": ["chart_id"],
        "backends": ["addon_http"],
        "description": "List indicators currently applied to a chart.",
    },
    "chart.indicator_add": {
        "required_args": ["indicator"],
        "optional_args": ["chart_id", "params"],
        "backends": ["addon_http"],
        "description": "Add an indicator to a chart.",
    },
    "chart.indicator_remove": {
        "required_args": ["indicator"],
        "optional_args": ["chart_id"],
        "backends": ["addon_http"],
        "description": "Remove an indicator from a chart.",
    },
    "chart.screenshot": {
        "required_args": [],
        "optional_args": ["chart_id", "name"],
        "backends": ["addon_http", "win32"],
        "description": "Capture screenshot of chart area.",
    },
    "chart.template_save": {
        "required_args": ["name"],
        "optional_args": ["chart_id"],
        "backends": ["addon_http"],
        "description": "Save current chart configuration as a named template.",
    },
    "chart.template_apply": {
        "required_args": ["name"],
        "optional_args": ["chart_id"],
        "backends": ["addon_http"],
        "description": "Apply a saved chart template to active or specified chart.",
    },

    # ── Strategy family ──────────────────────────────────────────────────
    "strategy.attach": {
        "required_args": ["strategy", "symbol"],
        "optional_args": ["period", "params"],
        "backends": ["addon_http"],
        "description": "Attach a strategy to a chart for live or sim execution.",
    },
    "strategy.detach": {
        "required_args": ["strategy"],
        "optional_args": [],
        "backends": ["addon_http"],
        "description": "Detach/remove a running strategy from its chart.",
    },
    "strategy.list_running": {
        "required_args": [],
        "optional_args": [],
        "backends": ["addon_http"],
        "description": "List all currently running strategies with state info.",
    },
    "strategy.state": {
        "required_args": ["strategy"],
        "optional_args": [],
        "backends": ["addon_http"],
        "description": "Get detailed state of a specific running strategy.",
    },
    "strategy.enable_autotrading": {
        "required_args": [],
        "optional_args": [],
        "backends": ["keyboard"],
        "description": "Toggle AutoTrading enabled/disabled (Ctrl+E).",
    },

    # ── Tester (Strategy Analyzer) family ────────────────────────────────
    "tester.open": {
        "required_args": [],
        "optional_args": [],
        "backends": ["keyboard"],
        "description": "Open the Strategy Analyzer window (Ctrl+R).",
    },
    "tester.configure": {
        "required_args": ["strategy", "symbol"],
        "optional_args": ["period_type", "period_value", "from_date", "to_date", "account"],
        "backends": ["keyboard"],
        "description": (
            "Configure Strategy Analyzer backtest parameters. Defaults when omitted: "
            "period_type=Minute, period_value=1, account=Sim101."
        ),
    },
    "tester.start": {
        "required_args": [],
        "optional_args": [],
        "backends": ["keyboard"],
        "description": "Start backtest run in Strategy Analyzer.",
    },
    "tester.status": {
        "required_args": [],
        "optional_args": ["since", "strategy"],
        "backends": ["file_write", "win32"],
        "description": "Check current backtest progress/status (new strategyanalyzerlogs xml since a timestamp).",
    },
    "tester.results": {
        "required_args": [],
        "optional_args": ["strategy", "since", "name"],
        "backends": ["file_write", "win32"],
        "description": "Retrieve backtest results (summary, trades, performance) parsed from strategyanalyzerlogs xml.",
    },
    "tester.list_results": {
        "required_args": [],
        "optional_args": ["strategy", "limit"],
        "backends": ["file_write"],
        "description": "List completed Strategy Analyzer backtest results, most recent first.",
    },

    # ── Trade family ─────────────────────────────────────────────────────
    "trade.place": {
        "required_args": ["account", "instrument", "action", "qty", "order_type"],
        "optional_args": ["price", "stop_loss", "take_profit", "tif"],
        "backends": ["dll_ati"],
        "description": "Place a new order via ATI DLL interface.",
    },
    "trade.cancel": {
        "required_args": ["order_id"],
        "optional_args": [],
        "backends": ["dll_ati"],
        "description": "Cancel a pending order by order ID.",
    },
    "trade.close_position": {
        "required_args": ["account", "instrument"],
        "optional_args": [],
        "backends": ["dll_ati"],
        "description": "Close an open position for given account and instrument.",
    },
    "trade.flatten_all": {
        "required_args": [],
        "optional_args": ["account"],
        "backends": ["dll_ati"],
        "description": "Flatten all open positions and cancel pending orders.",
    },
    "trade.reverse": {
        "required_args": ["account", "instrument", "action", "qty"],
        "optional_args": [],
        "backends": ["dll_ati"],
        "description": "Reverse an existing position (close and open opposite).",
    },

    # ── Account / Market family ──────────────────────────────────────────
    "account.info": {
        "required_args": ["account"],
        "optional_args": [],
        "backends": ["addon_http", "dll_ati"],
        "description": "Get account information (balance, buying power, P&L).",
    },
    "account.list": {
        "required_args": [],
        "optional_args": [],
        "backends": ["addon_http", "dll_ati"],
        "description": "List all connected trading accounts.",
    },
    "position.get": {
        "required_args": ["instrument", "account"],
        "optional_args": [],
        "backends": ["dll_ati"],
        "description": "Get position details for a specific instrument and account.",
    },
    "position.list": {
        "required_args": [],
        "optional_args": ["account"],
        "backends": ["addon_http"],
        "description": "List all open positions across accounts.",
    },
    "order.list": {
        "required_args": [],
        "optional_args": ["account"],
        "backends": ["dll_ati"],
        "description": "List all active orders.",
    },
    "order.status": {
        "required_args": ["order_id"],
        "optional_args": [],
        "backends": ["dll_ati"],
        "description": "Get status of a specific order by ID.",
    },
    "market_data.subscribe": {
        "required_args": ["instrument"],
        "optional_args": [],
        "backends": ["addon_http"],
        "description": "Subscribe to real-time market data for an instrument.",
    },
    "market_data.get": {
        "required_args": ["instrument"],
        "optional_args": [],
        "backends": ["addon_http", "dll_ati"],
        "description": "Get current quote (bid/ask/last) for an instrument.",
    },
    "market_data.history": {
        "required_args": ["instrument", "period", "bars_back"],
        "optional_args": ["end_date"],
        "backends": ["addon_http"],
        "description": "Retrieve historical bar data for an instrument.",
    },

    # ── Terminal family ──────────────────────────────────────────────────
    "terminal.detect": {
        "required_args": [],
        "optional_args": [],
        "backends": ["win32"],
        "description": "Check if NinjaTrader 8 process is running.",
    },
    "terminal.launch": {
        "required_args": [],
        "optional_args": ["config"],
        "backends": ["win32"],
        "description": "Launch NinjaTrader 8 application.",
    },
    "terminal.kill": {
        "required_args": [],
        "optional_args": [],
        "backends": ["win32"],
        "description": "Kill NinjaTrader 8 process.",
    },
    "terminal.focus": {
        "required_args": [],
        "optional_args": [],
        "backends": ["win32"],
        "description": "Bring NinjaTrader 8 window to foreground.",
    },
    "terminal.capture": {
        "required_args": [],
        "optional_args": ["name", "no_activate"],
        "backends": ["win32"],
        "description": "Capture NinjaTrader 8 window screenshot (background-safe via PrintWindow).",
    },
    "terminal.arrange": {
        "required_args": [],
        "optional_args": ["monitor_index"],
        "backends": ["win32"],
        "description": "Arrange NinjaTrader 8 window on specified monitor.",
    },

    # ── Logs family ──────────────────────────────────────────────────────
    "logs.output": {
        "required_args": [],
        "optional_args": ["lines", "tail"],
        "backends": ["addon_http", "file_write"],
        "description": "Read NinjaScript Output Window content.",
    },
    "logs.journal": {
        "required_args": [],
        "optional_args": ["lines", "tail"],
        "backends": ["file_write"],
        "description": "Read NinjaTrader log/journal file.",
    },
    "logs.trace": {
        "required_args": [],
        "optional_args": ["lines", "tail"],
        "backends": ["file_write"],
        "description": "Read NinjaTrader trace log file.",
    },

    # ── Bridge (AddOn) family ────────────────────────────────────────────
    "bridge.status": {
        "required_args": [],
        "optional_args": [],
        "backends": ["addon_http"],
        "description": "Check AddOn HTTP bridge health and connectivity.",
    },
    "bridge.deploy": {
        "required_args": [],
        "optional_args": [],
        "backends": ["auto"],
        "description": "Deploy the AI bridge AddOn to NinjaScript AddOns and compile.",
    },

    # ── System family ─────────────────────────────────────────────────────
    "system.capabilities": {
        "required_args": [],
        "optional_args": [],
        "backends": [],
        "description": (
            "Report per command implementation status (working, best_effort, or "
            "platform_gap) plus live backend health. Controller level, no backend."
        ),
    },

    # ── Macro family (multi-step compositions) ───────────────────────────
    "macro.develop_indicator": {
        "required_args": ["name", "content", "symbol"],
        "optional_args": ["period"],
        "backends": ["auto"],
        "description": "Write indicator + compile + open chart + attach + screenshot.",
    },
    "macro.develop_strategy": {
        "required_args": ["name", "content", "symbol"],
        "optional_args": ["period"],
        "backends": ["auto"],
        "description": (
            "Write strategy + compile + open chart + screenshot. Strategy attach is a "
            "confirmed NT8 platform gap; the macro reports how to attach manually "
            "instead of faking success."
        ),
    },
    "macro.compile_and_test": {
        "required_args": ["strategy", "symbol"],
        "optional_args": ["period_type", "period_value", "from_date", "to_date", "account", "timeout_seconds"],
        "backends": ["auto"],
        "description": "Compile + open/configure/start Strategy Analyzer + poll for completion + collect results + screenshot.",
    },
    "macro.iterate_strategy": {
        "required_args": ["name", "content", "symbol"],
        "optional_args": ["period_type", "period_value", "from_date", "to_date", "account", "timeout_seconds"],
        "backends": ["auto"],
        "description": "Write modified strategy code + compile_and_test + compare against the prior backtest result.",
    },
    "macro.chart_open_robust": {
        "required_args": ["symbol"],
        "optional_args": ["period"],
        "backends": ["auto"],
        "description": "Robust chart open with detection, retry, and recovery.",
    },
    "macro.full_dev_cycle": {
        "required_args": ["name", "content", "symbol"],
        "optional_args": ["period_type", "period_value", "from_date", "to_date", "account", "timeout_seconds"],
        "backends": ["auto"],
        "description": "Write strategy code + compile_and_test in one call.",
    },
}

_BACKEND_ACTION_MAP: dict[str, dict[str, str]] = {
    # code family -> file_write backend
    "code.write_strategy": {"file_write": "write_file"},
    "code.write_indicator": {"file_write": "write_file"},
    "code.write_addon": {"file_write": "write_file"},
    "code.read": {"file_write": "read_file"},
    "code.list": {"file_write": "list_files"},
    "code.delete": {"file_write": "delete_file"},
    "code.search": {"file_write": "search_files"},
    # compile family -> keyboard backend
    "compile.all": {"keyboard": "compile"},
    "compile.check": {"file_write": "compile_status"},
    "compile.errors": {"file_write": "parse_compile_errors"},
    # chart family
    "chart.list": {"addon_http": "get_charts"},
    "chart.open": {"keyboard": "open_chart"},
    "chart.close": {"addon_http": "close_chart", "keyboard": "close_chart"},
    "chart.switch_instrument": {"keyboard": "switch_instrument"},
    "chart.switch_timeframe": {"keyboard": "switch_timeframe"},
    "chart.indicator_list": {"addon_http": "get_indicators"},
    "chart.indicator_add": {"addon_http": "add_indicator"},
    "chart.indicator_remove": {"addon_http": "remove_indicator"},
    "chart.screenshot": {"addon_http": "screenshot", "win32": "capture_window"},
    "chart.template_save": {"addon_http": "save_template"},
    "chart.template_apply": {"addon_http": "apply_template"},
    # strategy family
    "strategy.attach": {"addon_http": "attach_strategy"},
    "strategy.detach": {"addon_http": "detach_strategy"},
    "strategy.list_running": {"addon_http": "get_strategies"},
    "strategy.state": {"addon_http": "get_strategy_state"},
    "strategy.enable_autotrading": {"keyboard": "toggle_autotrading"},
    # tester family
    "tester.open": {"keyboard": "open_tester"},
    "tester.configure": {"keyboard": "configure_tester"},
    "tester.start": {"keyboard": "start_tester"},
    "tester.status": {"file_write": "analyzer_status", "win32": "capture_window"},
    "tester.results": {"file_write": "analyzer_results", "win32": "capture_window"},
    "tester.list_results": {"file_write": "analyzer_list_results"},
    # trade family
    "trade.place": {"dll_ati": "place_order"},
    "trade.cancel": {"dll_ati": "cancel_order"},
    "trade.close_position": {"dll_ati": "close_position"},
    "trade.flatten_all": {"dll_ati": "flatten_all"},
    "trade.reverse": {"dll_ati": "reverse_position"},
    # account/market family
    "account.info": {"addon_http": "get_account_info", "dll_ati": "buying_power"},
    "account.list": {"addon_http": "get_accounts", "dll_ati": "get_accounts"},
    "position.get": {"dll_ati": "get_position"},
    "position.list": {"addon_http": "get_positions"},
    "order.list": {"dll_ati": "get_orders"},
    "order.status": {"dll_ati": "order_status"},
    "market_data.subscribe": {"addon_http": "subscribe_market_data"},
    "market_data.get": {"addon_http": "get_market_data", "dll_ati": "get_market_data"},
    "market_data.history": {"addon_http": "historical_bars"},
    # terminal family
    "terminal.detect": {"win32": "detect_process"},
    "terminal.launch": {"win32": "launch_process"},
    "terminal.kill": {"win32": "kill_process"},
    "terminal.focus": {"win32": "focus_window"},
    "terminal.capture": {"win32": "capture_window"},
    "terminal.arrange": {"win32": "arrange_window"},
    # logs family
    "logs.output": {"addon_http": "get_output_log", "file_write": "read_log"},
    "logs.journal": {"file_write": "read_log"},
    "logs.trace": {"file_write": "read_log"},
    # bridge family
    "bridge.status": {"addon_http": "health"},
    # bridge.deploy has no action map entry: run_command short circuits it via
    # _handle_bridge_deploy before backend resolution, so an action map entry
    # here would be dead code.
}

# ── system.capabilities status classification ──────────────────────────────
# platform_gap: NT8 has no supported programmatic API at all (confirmed by
# NinjaTrader staff, see research/NT8_AUTOMATION_RESEARCH_2026-07.md).
_PLATFORM_GAP_COMMANDS: frozenset[str] = frozenset({
    "strategy.attach",
    "strategy.detach",
    "chart.template_save",
    "chart.template_apply",
})

# best_effort: implemented via GUI keyboard/window automation or AddOn
# reflection, both of which can fail even when NT8 is healthy.
_BEST_EFFORT_COMMANDS: frozenset[str] = frozenset({
    "compile.all",
    "compile.check",
    "compile.errors",
    "chart.open",
    "chart.close",
    "chart.switch_instrument",
    "chart.switch_timeframe",
    "chart.indicator_add",
    "chart.indicator_remove",
    "strategy.enable_autotrading",
    "tester.configure",
    "tester.start",
    "tester.status",
    "tester.results",
    "tester.list_results",
    "terminal.launch",
    "terminal.kill",
    "terminal.focus",
    "terminal.capture",
    "terminal.arrange",
    "bridge.deploy",
    "macro.develop_indicator",
    "macro.develop_strategy",
    "macro.compile_and_test",
    "macro.iterate_strategy",
    "macro.chart_open_robust",
    "macro.full_dev_cycle",
})


class NT8ControlPlane:
    """Main command router for the NinjaTrader 8 AI control plane."""

    def __init__(
        self,
        nt8_data_dir: Path,
        backends: dict[str, BackendBase],
        workspace: Path,
    ) -> None:
        self.nt8_data_dir = Path(nt8_data_dir).resolve()
        self.backends = backends
        self.workspace = Path(workspace).resolve()
        self.state_dir = self.workspace / ".nt8skill" / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._visual_engine = VisualAssertionEngine(roi_registry=DEFAULT_ROI_REGISTRY)

    def run_command(
        self,
        command: str,
        args: dict[str, Any],
        backend: str = "auto",
        timeout_seconds: int = 120,
    ) -> ExecutionResult:
        cmd = command.strip()
        catalog_entry = NT8_COMMAND_CATALOG.get(cmd)
        if catalog_entry is None:
            return ExecutionResult(
                success=False,
                stderr=f"unknown nt8 command '{cmd}'",
                metadata={"failure_signal": "HARD_UNKNOWN_COMMAND"},
            )

        required = catalog_entry.get("required_args", [])
        missing = [arg for arg in required if arg not in args or args[arg] is None]
        if missing:
            return ExecutionResult(
                success=False,
                stderr=f"missing required args for '{cmd}': {missing}",
                metadata={"failure_signal": "HARD_VALIDATION"},
            )

        if cmd.startswith("macro."):
            return self._handle_macro(cmd, args, timeout_seconds)

        if cmd == "bridge.deploy":
            return self._handle_bridge_deploy(args, timeout_seconds)

        if cmd == "system.capabilities":
            return ExecutionResult(
                success=True,
                driver="nt8",
                stdout="capability report generated",
                metadata=self.command_capabilities(),
            )

        resolved_backend = self._resolve_backend(cmd, backend, catalog_entry)
        if resolved_backend is None:
            return ExecutionResult(
                success=False,
                stderr=f"command '{cmd}' does not support backend '{backend}'; available: {catalog_entry.get('backends', [])}",
                metadata={"failure_signal": "HARD_BACKEND_UNSUPPORTED"},
            )

        backend_instance = self.backends.get(resolved_backend)
        if backend_instance is None:
            return ExecutionResult(
                success=False,
                stderr=f"backend '{resolved_backend}' not registered",
                metadata={"failure_signal": "HARD_BACKEND_UNSUPPORTED"},
            )

        if not backend_instance.is_available():
            return ExecutionResult(
                success=False,
                stderr=f"backend '{resolved_backend}' is not available",
                metadata={"failure_signal": "SOFT_BACKEND_UNAVAILABLE"},
            )

        action_map = _BACKEND_ACTION_MAP.get(cmd, {})
        action = action_map.get(resolved_backend, cmd.split(".")[-1])

        enriched_args = dict(args)
        if cmd == "code.write_indicator":
            enriched_args.setdefault("type", "indicator")
        elif cmd == "code.write_addon":
            enriched_args.setdefault("type", "addon")
        elif cmd == "code.write_strategy":
            enriched_args.setdefault("type", "strategy")
        elif cmd == "tester.configure":
            # CONTRACT.md's catalog arg name is "symbol" (matches the rest of the
            # catalog, e.g. chart.open); the live keyboard backend template
            # placeholders read "instrument". Mirror the value so either name works.
            if "symbol" in enriched_args:
                enriched_args.setdefault("instrument", enriched_args["symbol"])
        enriched_args["_command"] = cmd
        enriched_args["_timeout_seconds"] = timeout_seconds
        enriched_args["_nt8_data_dir"] = str(self.nt8_data_dir)

        return backend_instance.execute(action, enriched_args)

    def _resolve_backend(self, command: str, requested: str, catalog_entry: dict[str, Any]) -> str | None:
        available_backends = catalog_entry.get("backends", [])
        if requested != "auto":
            return requested if requested in available_backends else None

        action_map = _BACKEND_ACTION_MAP.get(command, {})
        for candidate in available_backends:
            if candidate == "auto":
                continue
            backend_instance = self.backends.get(candidate)
            if backend_instance is not None and backend_instance.is_available() and candidate in action_map:
                return candidate

        for candidate in available_backends:
            if candidate == "auto":
                continue
            backend_instance = self.backends.get(candidate)
            if backend_instance is not None and backend_instance.is_available():
                return candidate

        non_auto = [b for b in available_backends if b != "auto"]
        return non_auto[0] if non_auto else None

    def health_check(self) -> dict[str, Any]:
        backends_status: dict[str, Any] = {}
        for name, backend in self.backends.items():
            try:
                backends_status[name] = {
                    "available": backend.is_available(),
                }
            except Exception as exc:
                backends_status[name] = {"available": False, "error": str(exc)}

        nt8_running = False
        win32 = self.backends.get("win32")
        if win32 is not None and win32.is_available():
            try:
                detect_result = win32.execute("detect_process", {})
                # success only means the probe ran; the answer is in metadata.
                nt8_running = bool(detect_result.metadata.get("running"))
            except Exception:
                pass

        addon_ok = backends_status.get("addon_http", {}).get("available", False)

        dll_ok = False
        dll = self.backends.get("dll_ati")
        if dll is not None and dll.is_available():
            dll_ok = True

        return {
            "nt8_running": nt8_running,
            "addon_connected": addon_ok,
            "dll_available": dll_ok,
            "backends": backends_status,
            "nt8_data_dir": str(self.nt8_data_dir),
            "workspace": str(self.workspace),
            "command_count": len(NT8_COMMAND_CATALOG),
        }

    def command_catalog(self) -> dict[str, Any]:
        return {
            cmd: {
                "description": entry.get("description", ""),
                "required_args": entry.get("required_args", []),
                "optional_args": entry.get("optional_args", []),
                "backends": entry.get("backends", []),
            }
            for cmd, entry in NT8_COMMAND_CATALOG.items()
        }

    def shortcuts(self) -> list[dict[str, Any]]:
        return list_nt8_shortcuts()

    def command_capabilities(self) -> dict[str, Any]:
        commands: dict[str, Any] = {}
        for cmd, entry in NT8_COMMAND_CATALOG.items():
            if cmd in _PLATFORM_GAP_COMMANDS:
                status = "platform_gap"
            elif cmd in _BEST_EFFORT_COMMANDS:
                status = "best_effort"
            else:
                status = "working"

            command_report: dict[str, Any] = {
                "status": status,
                "backends": entry.get("backends", []),
                "description": entry.get("description", ""),
            }
            if status == "platform_gap":
                command_report["remediation"] = (
                    "NT8 has no supported programmatic API for this action, confirmed by "
                    "NinjaTrader staff. Use the NT8 GUI directly. For strategy.attach: set "
                    "IsEnabled=true in State.SetDefaults so the strategy auto enables when "
                    "its workspace loads."
                )
            commands[cmd] = command_report

        return {
            "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
            "commands": commands,
            "backend_health": self.health_check(),
        }

    def perform_visual_verification(
        self,
        *,
        command: str,
        args: dict[str, Any],
        result: ExecutionResult,
        verify_mode: str,
        trace_id: str | None = None,
        instance_id: str | None = None,
    ) -> dict[str, Any]:
        requirements = DEFAULT_VISUAL_REQUIREMENTS.get(command)
        if not requirements:
            return {"performed": False, "passed": True, "assertions": [], "reason": "no_visual_requirements"}

        artifacts = result.artifacts if isinstance(result.artifacts, list) else []
        image_path: Path | None = None
        for artifact in artifacts:
            path = Path(str(artifact))
            if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp") and path.exists():
                image_path = path
                break

        if image_path is None:
            return {
                "performed": False,
                "passed": True,
                "assertions": [],
                "reason": "no_screenshot_artifact",
            }

        return self._visual_engine.evaluate(
            image_path=image_path,
            assertions=requirements,
            retries=1,
            retry_delay_seconds=0.2,
        )

    # ── Macro handlers ───────────────────────────────────────────────────

    def _handle_macro(self, command: str, args: dict[str, Any], timeout_seconds: int) -> ExecutionResult:
        handler = self._macro_dispatch.get(command)
        if handler is None:
            return ExecutionResult(
                success=False,
                stderr=f"no macro handler for '{command}'",
                metadata={"failure_signal": "HARD_UNKNOWN_COMMAND"},
            )
        return handler(self, args, timeout_seconds)

    def _macro_develop_indicator(self, args: dict[str, Any], timeout_seconds: int) -> ExecutionResult:
        steps: list[dict[str, Any]] = []
        name = args["name"]
        content = args["content"]
        symbol = args["symbol"]
        period = args.get("period", "1 Min")

        write_result = self.run_command("code.write_indicator", {"name": name, "content": content}, timeout_seconds=timeout_seconds)
        steps.append({"step": "write_indicator", "success": write_result.success, "stderr": write_result.stderr})
        if not write_result.success:
            return ExecutionResult(
                success=False,
                stderr=f"macro.develop_indicator failed at write: {write_result.stderr}",
                metadata={"steps": steps, "failure_stage": "write_indicator"},
            )

        compile_result = self.run_command("compile.all", {}, timeout_seconds=timeout_seconds)
        steps.append({"step": "compile", "success": compile_result.success, "stderr": compile_result.stderr})
        if not compile_result.success:
            return ExecutionResult(
                success=False,
                stderr=f"macro.develop_indicator failed at compile: {compile_result.stderr}",
                metadata={"steps": steps, "failure_stage": "compile"},
            )

        chart_result = self.run_command("chart.open", {"symbol": symbol, "period": period}, timeout_seconds=timeout_seconds)
        steps.append({"step": "chart_open", "success": chart_result.success, "stderr": chart_result.stderr})

        add_result = self.run_command("chart.indicator_add", {"indicator": name}, timeout_seconds=timeout_seconds)
        steps.append({"step": "indicator_add", "success": add_result.success, "stderr": add_result.stderr})

        screenshot_result = self.run_command("chart.screenshot", {"name": f"dev_{name}"}, timeout_seconds=timeout_seconds)
        steps.append({"step": "screenshot", "success": screenshot_result.success})

        all_ok = all(s["success"] for s in steps)
        return ExecutionResult(
            success=all_ok,
            driver="nt8",
            stdout=f"develop_indicator '{name}' completed: {len([s for s in steps if s['success']])}/{len(steps)} steps OK",
            artifacts=screenshot_result.artifacts if screenshot_result.success else [],
            metadata={"steps": steps},
        )

    def _macro_develop_strategy(self, args: dict[str, Any], timeout_seconds: int) -> ExecutionResult:
        # strategy.attach is a confirmed NT8 platform gap (no supported AddOn API to
        # enable a strategy). This macro does everything that IS automatable (write,
        # compile, open chart, screenshot) and then honestly reports that attach must
        # be done via the chart GUI or workspace auto enable. It never fakes success
        # on the attach step.
        steps: list[dict[str, Any]] = []
        name = args["name"]
        content = args["content"]
        symbol = args["symbol"]
        period = args.get("period", "1 Min")

        write_result = self.run_command("code.write_strategy", {"name": name, "content": content}, timeout_seconds=timeout_seconds)
        steps.append({"step": "write_strategy", "success": write_result.success, "stderr": write_result.stderr})
        if not write_result.success:
            return ExecutionResult(
                success=False,
                stderr=f"macro.develop_strategy failed at write: {write_result.stderr}",
                metadata={"steps": steps, "failure_stage": "write_strategy"},
            )

        compile_result = self.run_command("compile.all", {}, timeout_seconds=timeout_seconds)
        steps.append({"step": "compile", "success": compile_result.success, "stderr": compile_result.stderr})
        if not compile_result.success:
            errors_result = self.run_command("compile.errors", {}, timeout_seconds=30)
            steps.append({"step": "compile_errors", "success": errors_result.success})
            return ExecutionResult(
                success=False,
                stderr=f"macro.develop_strategy failed at compile: {compile_result.stderr}",
                metadata={
                    "steps": steps,
                    "failure_stage": "compile",
                    "compile": compile_result.metadata,
                    "compile_errors": errors_result.metadata if errors_result.success else {},
                },
            )

        chart_result = self.run_command("chart.open", {"symbol": symbol, "period": period}, timeout_seconds=timeout_seconds)
        steps.append({"step": "chart_open", "success": chart_result.success, "stderr": chart_result.stderr})

        screenshot_result = self.run_command("chart.screenshot", {"name": f"dev_{name}"}, timeout_seconds=timeout_seconds)
        steps.append({"step": "screenshot", "success": screenshot_result.success})

        attach_note = (
            "strategy.attach is a confirmed NT8 platform gap: there is no supported AddOn "
            f"API to enable a strategy. Attach '{name}' manually from the chart GUI (right "
            "click the chart, Strategies, add it), or set IsEnabled=true in the strategy's "
            "State.SetDefaults so it auto enables when its workspace loads."
        )
        steps.append({
            "step": "strategy_attach",
            "success": False,
            "error_code_hint": "NOT_SUPPORTED_BY_PLATFORM",
            "note": attach_note,
        })

        core_ok = write_result.success and compile_result.success and chart_result.success
        return ExecutionResult(
            success=core_ok,
            driver="nt8",
            stdout=(
                f"develop_strategy '{name}': code written and compiled, chart opened. "
                f"Attach step NOT automated. {attach_note}"
            ),
            artifacts=screenshot_result.artifacts if screenshot_result.success else [],
            metadata={"steps": steps, "attach_required_manual": True, "attach_note": attach_note},
        )

    def _macro_compile_and_test(self, args: dict[str, Any], timeout_seconds: int) -> ExecutionResult:
        steps: list[dict[str, Any]] = []
        strategy = args["strategy"]
        symbol = args["symbol"]

        compile_result = self.run_command("compile.all", {}, timeout_seconds=timeout_seconds)
        steps.append({"step": "compile", "success": compile_result.success, "stderr": compile_result.stderr})
        if not compile_result.success:
            errors_result = self.run_command("compile.errors", {}, timeout_seconds=30)
            steps.append({"step": "compile_errors", "success": errors_result.success})
            return ExecutionResult(
                success=False,
                stderr=f"macro.compile_and_test aborted: compile failed: {compile_result.stderr}",
                metadata={
                    "steps": steps,
                    "failure_stage": "compile",
                    "compile": compile_result.metadata,
                    "compile_errors": errors_result.metadata if errors_result.success else {},
                },
            )

        t0 = datetime.now(tz=timezone.utc).isoformat()

        open_result = self.run_command("tester.open", {}, timeout_seconds=timeout_seconds)
        steps.append({"step": "tester_open", "success": open_result.success, "stderr": open_result.stderr})

        configure_args: dict[str, Any] = {"strategy": strategy, "symbol": symbol}
        for opt in ("period_type", "period_value", "from_date", "to_date", "account"):
            if opt in args:
                configure_args[opt] = args[opt]

        configure_result = self.run_command("tester.configure", configure_args, timeout_seconds=timeout_seconds)
        steps.append({"step": "tester_configure", "success": configure_result.success, "stderr": configure_result.stderr})
        if not configure_result.success:
            return ExecutionResult(
                success=False,
                stderr=f"macro.compile_and_test failed at configure: {configure_result.stderr}",
                metadata={"steps": steps, "failure_stage": "tester_configure", "compile": compile_result.metadata},
            )

        start_result = self.run_command("tester.start", {}, timeout_seconds=timeout_seconds)
        steps.append({"step": "tester_start", "success": start_result.success, "stderr": start_result.stderr})
        if not start_result.success:
            return ExecutionResult(
                success=False,
                stderr=f"macro.compile_and_test failed at start: {start_result.stderr}",
                metadata={"steps": steps, "failure_stage": "tester_start", "compile": compile_result.metadata},
            )

        poll_timeout_seconds = max(1, int(args.get("timeout_seconds", 300)))
        deadline = time.time() + poll_timeout_seconds
        backtest_done = False
        status_meta: dict[str, Any] = {}
        while time.time() < deadline:
            status_result = self.run_command(
                "tester.status",
                {"since": t0, "strategy": strategy},
                backend="file_write",
                timeout_seconds=15,
            )
            steps.append({"step": "tester_poll", "success": status_result.success})
            meta = status_result.metadata if isinstance(status_result.metadata, dict) else {}
            state = str(meta.get("state", "")).lower()
            if status_result.success and (bool(meta.get("found")) or state in ("complete", "completed", "done", "finished")):
                backtest_done = True
                status_meta = meta
                break
            time.sleep(5.0)

        if not backtest_done:
            return ExecutionResult(
                success=False,
                stderr="macro.compile_and_test: backtest did not complete within timeout",
                metadata={
                    "steps": steps,
                    "failure_stage": "tester_wait",
                    "error_code_hint": "ANALYZER_NOT_OPEN",
                    "compile": compile_result.metadata,
                    "last_status": status_meta,
                    "since": t0,
                },
            )

        results_result = self.run_command(
            "tester.results",
            {"since": t0, "strategy": strategy},
            backend="file_write",
            timeout_seconds=timeout_seconds,
        )
        steps.append({"step": "tester_results", "success": results_result.success, "stderr": results_result.stderr})

        screenshot_result = self.run_command("chart.screenshot", {"name": f"backtest_{strategy}"}, timeout_seconds=20)
        steps.append({"step": "screenshot", "success": screenshot_result.success})
        screenshot_path = screenshot_result.artifacts[0] if screenshot_result.success and screenshot_result.artifacts else None

        return ExecutionResult(
            success=results_result.success,
            driver="nt8",
            stdout=results_result.stdout,
            artifacts=screenshot_result.artifacts if screenshot_result.success else [],
            metadata={
                "steps": steps,
                "compile": compile_result.metadata,
                "backtest_stats": results_result.metadata,
                "screenshot_path": screenshot_path,
                "since": t0,
            },
        )

    def _macro_iterate_strategy(self, args: dict[str, Any], timeout_seconds: int) -> ExecutionResult:
        steps: list[dict[str, Any]] = []
        name = args["name"]
        content = args["content"]
        symbol = args["symbol"]

        prior_result = self.run_command("tester.list_results", {"strategy": name, "limit": 1}, timeout_seconds=15)
        steps.append({"step": "list_prior_results", "success": prior_result.success})
        prior_stats = None
        if prior_result.success:
            prior_meta = prior_result.metadata if isinstance(prior_result.metadata, dict) else {}
            results_list = prior_meta.get("results", [])
            if isinstance(results_list, list) and results_list:
                prior_stats = results_list[0]

        write_result = self.run_command("code.write_strategy", {"name": name, "content": content}, timeout_seconds=timeout_seconds)
        steps.append({"step": "write_strategy", "success": write_result.success, "stderr": write_result.stderr})
        if not write_result.success:
            return ExecutionResult(
                success=False,
                stderr=f"macro.iterate_strategy failed at write: {write_result.stderr}",
                metadata={"steps": steps, "failure_stage": "write_strategy"},
            )

        test_args: dict[str, Any] = {"strategy": name, "symbol": symbol}
        for opt in ("period_type", "period_value", "from_date", "to_date", "account", "timeout_seconds"):
            if opt in args:
                test_args[opt] = args[opt]

        test_result = self._macro_compile_and_test(test_args, timeout_seconds)
        steps.append({"step": "compile_and_test", "success": test_result.success, "stderr": test_result.stderr})

        test_meta = test_result.metadata if isinstance(test_result.metadata, dict) else {}
        after_stats = test_meta.get("backtest_stats") if test_result.success else None

        return ExecutionResult(
            success=test_result.success,
            driver="nt8",
            stdout=f"iterate_strategy '{name}' completed",
            artifacts=test_result.artifacts,
            metadata={
                "steps": steps,
                "before": prior_stats,
                "after": after_stats,
                "compile": test_meta.get("compile"),
                "screenshot_path": test_meta.get("screenshot_path"),
                "test_metadata": test_result.metadata,
            },
        )

    def _macro_chart_open_robust(self, args: dict[str, Any], timeout_seconds: int) -> ExecutionResult:
        symbol = args["symbol"]
        period = args.get("period")
        steps: list[dict[str, Any]] = []

        detect_result = self.run_command("terminal.detect", {}, timeout_seconds=10)
        steps.append({"step": "detect", "success": detect_result.success})

        if not detect_result.success:
            launch_result = self.run_command("terminal.launch", {}, timeout_seconds=30)
            steps.append({"step": "launch", "success": launch_result.success})
            if not launch_result.success:
                return ExecutionResult(
                    success=False,
                    stderr="macro.chart_open_robust: could not launch NT8",
                    metadata={"steps": steps, "failure_stage": "launch"},
                )
            time.sleep(5.0)

        chart_args: dict[str, Any] = {"symbol": symbol}
        if period:
            chart_args["period"] = period

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            chart_result = self.run_command("chart.open", chart_args, timeout_seconds=timeout_seconds)
            steps.append({"step": f"chart_open_attempt_{attempt}", "success": chart_result.success})
            if chart_result.success:
                screenshot_result = self.run_command("chart.screenshot", {"name": f"robust_{symbol}"}, timeout_seconds=15)
                steps.append({"step": "screenshot", "success": screenshot_result.success})
                return ExecutionResult(
                    success=True,
                    driver="nt8",
                    stdout=f"chart opened for {symbol} on attempt {attempt}",
                    artifacts=screenshot_result.artifacts if screenshot_result.success else [],
                    metadata={"steps": steps, "attempts": attempt},
                )
            if attempt < max_attempts:
                time.sleep(2.0)

        return ExecutionResult(
            success=False,
            stderr=f"macro.chart_open_robust: failed after {max_attempts} attempts",
            metadata={"steps": steps, "failure_stage": "chart_open"},
        )

    def _macro_full_dev_cycle(self, args: dict[str, Any], timeout_seconds: int) -> ExecutionResult:
        steps: list[dict[str, Any]] = []
        name = args["name"]
        content = args["content"]
        symbol = args["symbol"]

        write_result = self.run_command("code.write_strategy", {"name": name, "content": content}, timeout_seconds=timeout_seconds)
        steps.append({"step": "write_strategy", "success": write_result.success, "stderr": write_result.stderr})
        if not write_result.success:
            return ExecutionResult(
                success=False,
                stderr=f"macro.full_dev_cycle failed at write: {write_result.stderr}",
                metadata={"steps": steps, "failure_stage": "write_strategy"},
            )

        test_args: dict[str, Any] = {"strategy": name, "symbol": symbol}
        for opt in ("period_type", "period_value", "from_date", "to_date", "account", "timeout_seconds"):
            if opt in args:
                test_args[opt] = args[opt]

        test_result = self._macro_compile_and_test(test_args, timeout_seconds)
        steps.append({"step": "compile_and_test", "success": test_result.success, "stderr": test_result.stderr})

        test_meta = test_result.metadata if isinstance(test_result.metadata, dict) else {}
        merged_metadata = dict(test_meta)
        merged_metadata["steps"] = steps + list(test_meta.get("steps", []))

        return ExecutionResult(
            success=test_result.success,
            driver="nt8",
            stdout=f"full_dev_cycle '{name}' completed",
            stderr=test_result.stderr,
            artifacts=test_result.artifacts,
            metadata=merged_metadata,
        )

    def _handle_bridge_deploy(self, args: dict[str, Any], timeout_seconds: int) -> ExecutionResult:
        steps: list[dict[str, Any]] = []
        addon_cs = Path(__file__).parent / "assets" / "nt8" / "AntigravityBridgeAddOn.cs"
        if not addon_cs.exists():
            return ExecutionResult(
                success=False,
                stderr=f"Bridge AddOn source not found at {addon_cs}",
                metadata={"failure_stage": "locate_source"},
            )

        content = addon_cs.read_text(encoding="utf-8")
        write_result = self.run_command(
            "code.write_addon",
            {"name": "AntigravityBridgeAddOn", "content": content},
            timeout_seconds=timeout_seconds,
        )
        steps.append({"step": "write_addon", "success": write_result.success, "stderr": write_result.stderr})
        if not write_result.success:
            return ExecutionResult(
                success=False,
                stderr=f"bridge.deploy failed at write: {write_result.stderr}",
                metadata={"steps": steps, "failure_stage": "write_addon"},
            )

        compile_result = self.run_command("compile.all", {}, timeout_seconds=timeout_seconds)
        steps.append({"step": "compile", "success": compile_result.success, "stderr": compile_result.stderr})

        return ExecutionResult(
            success=compile_result.success,
            driver="nt8",
            stdout="Bridge AddOn deployed" + (" and compiled" if compile_result.success else " but compile may have failed"),
            metadata={"steps": steps},
        )

    _macro_dispatch: dict[str, Any] = {
        "macro.develop_indicator": _macro_develop_indicator,
        "macro.develop_strategy": _macro_develop_strategy,
        "macro.compile_and_test": _macro_compile_and_test,
        "macro.iterate_strategy": _macro_iterate_strategy,
        "macro.chart_open_robust": _macro_chart_open_robust,
        "macro.full_dev_cycle": _macro_full_dev_cycle,
    }
