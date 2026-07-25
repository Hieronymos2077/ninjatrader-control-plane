from __future__ import annotations
import os
import time
import threading
from pathlib import Path
from typing import Any

try:
    from .base import BackendBase, ExecutionResult
except ImportError:
    from base import BackendBase, ExecutionResult


def _find_nt8_data_dir() -> Path:
    docs = Path.home() / "Documents" / "NinjaTrader 8"
    if docs.exists():
        return docs
    onedrive = Path.home() / "OneDrive" / "Documents" / "NinjaTrader 8"
    if onedrive.exists():
        return onedrive
    return docs


class DllAtiBackend(BackendBase):
    """ATI (Automated Trading Interface) backend.

    Primary path: file-based OIF (Order Instruction Files).
    Writes command files to incoming/, reads results from outgoing/.
    """

    name = "dll_ati"

    def __init__(self, nt8_data_dir: Path | None = None):
        self.nt8_root = nt8_data_dir or _find_nt8_data_dir()
        self.incoming = self.nt8_root / "incoming"
        self.outgoing = self.nt8_root / "outgoing"
        self._counter = int(time.time() * 1000) % 1_000_000
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        return self.nt8_root.exists()

    def execute(self, action: str, args: dict[str, Any]) -> ExecutionResult:
        dispatch = {
            "place_order": self._place_order,
            "cancel_order": self._cancel_order,
            "cancel_all_orders": self._cancel_all_orders,
            "change_order": self._change_order,
            "close_position": self._close_position,
            "close_strategy": self._close_strategy,
            "flatten_all": self._flatten_all,
            "reverse_position": self._reverse_position,
            "get_position": self._get_position,
            "get_orders": self._get_orders_outgoing,
            "order_status": self._order_status,
            "get_accounts": lambda a: self._not_supported_via_file(action, a),
            "subscribe_market_data": lambda a: self._not_supported_via_file(action, a),
            "get_market_data": lambda a: self._not_supported_via_file(action, a),
            "buying_power": lambda a: self._not_supported_via_file(action, a),
            "cash_value": lambda a: self._not_supported_via_file(action, a),
            "realized_pnl": lambda a: self._not_supported_via_file(action, a),
        }
        handler = dispatch.get(action)
        if handler is None:
            return ExecutionResult(success=False, driver=self.name, stderr=f"Unknown action '{action}'")
        try:
            return handler(args)
        except Exception as exc:
            return ExecutionResult(success=False, driver=self.name, stderr=str(exc))

    def _not_supported_via_file(self, action: str, args: dict) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            driver=self.name,
            stderr=(
                f"'{action}' is not supported via file based ATI. This platform only supports order "
                f"placement, cancel, and position queries through the incoming/outgoing folders. "
                f"Use the addon_http backend instead for '{action}' (see the command catalog mapping, "
                f"e.g. market_data.get / account.info route to addon_http first)."
            ),
            metadata={"not_supported": True, "suggestion": "addon_http", "action": action},
        )

    # ── OIF file writing ──────────────────────────────────────────────

    def _next_filename(self) -> Path:
        with self._lock:
            self._counter += 1
            return self.incoming / f"oif{self._counter}.txt"

    def _write_oif(self, command: str) -> Path:
        self.incoming.mkdir(parents=True, exist_ok=True)
        path = self._next_filename()
        path.write_text(command, encoding="utf-8")
        return path

    def _field(self, args: dict, key: str, default: str = "") -> str:
        val = args.get(key, default)
        if val is None:
            return ""
        return str(val)

    def _build_line(self, cmd: str, args: dict) -> str:
        account = self._field(args, "account")
        instrument = self._field(args, "instrument")
        action = self._field(args, "action")
        qty = self._field(args, "qty")
        order_type = self._field(args, "order_type")
        limit_price = self._field(args, "limit_price")
        stop_price = self._field(args, "stop_price")
        tif = self._field(args, "tif")
        oco = self._field(args, "oco")
        order_id = self._field(args, "order_id")
        strategy = self._field(args, "strategy")
        strategy_id = self._field(args, "strategy_id")

        return ";".join([
            cmd, account, instrument, action, qty, order_type,
            limit_price, stop_price, tif, oco, order_id, strategy, strategy_id,
        ])

    # ── actions: write commands ───────────────────────────────────────

    def _place_order(self, args: dict) -> ExecutionResult:
        for required in ("account", "instrument", "action", "qty", "order_type"):
            if required not in args:
                return ExecutionResult(success=False, driver=self.name, stderr=f"Missing required arg: {required}")

        args.setdefault("tif", "DAY")
        line = self._build_line("PLACE", args)
        path = self._write_oif(line)

        order_id = self._field(args, "order_id")
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Order file written: {path.name}",
            artifacts=[str(path)],
            metadata={"oif_file": str(path), "order_id": order_id, "command": line},
        )

    def _cancel_order(self, args: dict) -> ExecutionResult:
        order_id = args.get("order_id")
        strategy_id = args.get("strategy_id", "")
        if not order_id and not strategy_id:
            return ExecutionResult(success=False, driver=self.name, stderr="Need order_id or strategy_id")

        line = self._build_line("CANCEL", {
            "account": args.get("account", ""),
            "order_id": order_id or "",
            "strategy_id": strategy_id,
        })
        path = self._write_oif(line)
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Cancel order file written: {path.name}",
            artifacts=[str(path)],
            metadata={"oif_file": str(path), "command": line},
        )

    def _cancel_all_orders(self, args: dict) -> ExecutionResult:
        line = "CANCELALLORDERS;;;;;;;;;;;;"
        path = self._write_oif(line)
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Cancel all orders file written: {path.name}",
            artifacts=[str(path)],
            metadata={"oif_file": str(path), "command": line},
        )

    def _change_order(self, args: dict) -> ExecutionResult:
        line = self._build_line("CHANGE", args)
        path = self._write_oif(line)
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Change order file written: {path.name}",
            artifacts=[str(path)],
            metadata={"oif_file": str(path), "command": line},
        )

    def _close_position(self, args: dict) -> ExecutionResult:
        for required in ("account", "instrument"):
            if required not in args:
                return ExecutionResult(success=False, driver=self.name, stderr=f"Missing required arg: {required}")

        line = self._build_line("CLOSEPOSITION", args)
        path = self._write_oif(line)
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Close position file written: {path.name}",
            artifacts=[str(path)],
            metadata={"oif_file": str(path), "command": line},
        )

    def _close_strategy(self, args: dict) -> ExecutionResult:
        strategy_id = args.get("strategy_id", "")
        if not strategy_id:
            return ExecutionResult(success=False, driver=self.name, stderr="Missing required arg: strategy_id")

        line = self._build_line("CLOSESTRATEGY", {"strategy_id": strategy_id})
        path = self._write_oif(line)
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Close strategy file written: {path.name}",
            artifacts=[str(path)],
            metadata={"oif_file": str(path), "command": line},
        )

    def _flatten_all(self, args: dict) -> ExecutionResult:
        line = "FLATTENEVERYTHING;;;;;;;;;;;;"
        path = self._write_oif(line)
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Flatten everything file written: {path.name}",
            artifacts=[str(path)],
            metadata={"oif_file": str(path), "command": line},
        )

    def _reverse_position(self, args: dict) -> ExecutionResult:
        for required in ("account", "instrument", "action", "qty", "order_type"):
            if required not in args:
                return ExecutionResult(success=False, driver=self.name, stderr=f"Missing required arg: {required}")

        args.setdefault("tif", "DAY")
        line = self._build_line("REVERSEPOSITION", args)
        path = self._write_oif(line)
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Reverse position file written: {path.name}",
            artifacts=[str(path)],
            metadata={"oif_file": str(path), "command": line},
        )

    # ── actions: read outgoing status ─────────────────────────────────

    def _order_status(self, args: dict) -> ExecutionResult:
        order_id = args.get("order_id")
        if not order_id:
            return ExecutionResult(success=False, driver=self.name, stderr="Missing required arg: order_id")

        status_file = self.outgoing / f"{order_id}.txt"
        if not status_file.exists():
            return ExecutionResult(
                success=True, driver=self.name,
                stdout="No status file yet (order may be pending)",
                metadata={"order_id": order_id, "status": "UNKNOWN"},
            )

        content = status_file.read_text(encoding="utf-8", errors="replace").strip()
        parts = content.split(";")
        state = parts[0] if len(parts) > 0 else "UNKNOWN"
        filled = parts[1] if len(parts) > 1 else "0"
        avg_price = parts[2] if len(parts) > 2 else "0"

        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Order {order_id}: {state} filled={filled} avg_price={avg_price}",
            metadata={
                "order_id": order_id,
                "state": state,
                "filled_amount": filled,
                "avg_fill_price": avg_price,
                "raw": content,
            },
        )

    def _get_position(self, args: dict) -> ExecutionResult:
        instrument = args.get("instrument", "")
        account = args.get("account", "")

        if not instrument:
            return ExecutionResult(success=False, driver=self.name, stderr="Missing required arg: instrument")

        if not self.outgoing.exists():
            return ExecutionResult(
                success=True, driver=self.name,
                stdout="No outgoing directory",
                metadata={"position": "FLAT", "qty": "0", "avg_entry": "0"},
            )

        # Position files: "{Instrument} {Exchange}_{Account}_Position.txt"
        # Try to find matching file by instrument prefix
        matches = []
        for f in self.outgoing.glob("*_Position.txt"):
            fname = f.name
            if instrument.upper() in fname.upper():
                if not account or account.upper() in fname.upper():
                    matches.append(f)

        if not matches:
            return ExecutionResult(
                success=True, driver=self.name,
                stdout=f"No position file for {instrument}",
                metadata={"instrument": instrument, "position": "FLAT", "qty": "0", "avg_entry": "0"},
            )

        content = matches[0].read_text(encoding="utf-8", errors="replace").strip()
        parts = content.split(";")
        direction = parts[0] if len(parts) > 0 else "FLAT"
        qty = parts[1] if len(parts) > 1 else "0"
        avg_entry = parts[2] if len(parts) > 2 else "0"

        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Position {instrument}: {direction} qty={qty} entry={avg_entry}",
            metadata={
                "instrument": instrument,
                "position": direction,
                "qty": qty,
                "avg_entry": avg_entry,
                "raw": content,
                "file": str(matches[0]),
            },
        )

    def _get_orders_outgoing(self, args: dict) -> ExecutionResult:
        if not self.outgoing.exists():
            return ExecutionResult(
                success=True, driver=self.name,
                stdout="No outgoing directory",
                metadata={"orders": []},
            )

        orders = []
        for f in self.outgoing.glob("*.txt"):
            if "_Position" in f.name or f.name in ("CONNECTED.txt", "DISCONNECTED.txt"):
                continue
            content = f.read_text(encoding="utf-8", errors="replace").strip()
            parts = content.split(";")
            if len(parts) >= 3:
                orders.append({
                    "order_id": f.stem,
                    "state": parts[0],
                    "filled": parts[1],
                    "avg_price": parts[2],
                    "raw": content,
                })

        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Found {len(orders)} order status files",
            metadata={"orders": orders},
        )
