from __future__ import annotations
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from .base import BackendBase, ExecutionResult
except ImportError:
    from base import BackendBase, ExecutionResult


class AddonHttpBackend(BackendBase):
    name = "addon_http"

    def __init__(self, host: str = "127.0.0.1", port: int = 8089, timeout: int = 30):
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self._captures_dir = Path.home() / "Documents" / "NinjaTrader 8" / "captures"

    def is_available(self) -> bool:
        try:
            # Use short timeout for availability check to avoid blocking health endpoint
            req = urllib.request.Request(self.base_url + "/health", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception:
            return False

    def execute(self, action: str, args: dict[str, Any]) -> ExecutionResult:
        dispatch = {
            "health": self._health,
            "get_version": self._get_version,
            "get_charts": self._get_charts,
            "get_indicators": self._get_indicators,
            "add_indicator": self._add_indicator,
            "remove_indicator": self._remove_indicator,
            "screenshot": self._screenshot,
            "get_accounts": self._get_accounts,
            "get_account_info": self._get_account_info,
            "get_positions": self._get_positions,
            "get_orders": self._get_orders,
            "get_strategies": self._get_strategies,
            "get_market_data": self._get_market_data,
            "subscribe_market_data": self._subscribe_market_data,
            "unsubscribe_market_data": self._unsubscribe_market_data,
            "historical_bars": self._historical_bars,
            "get_connections": self._get_connections,
            "get_output_log": self._get_output_log,
            "get_output": self._get_output_log,
            "close_chart": self._close_chart,
            "save_template": self._save_template,
            "apply_template": self._apply_template,
            "attach_strategy": self._attach_strategy,
            "detach_strategy": self._detach_strategy,
            "get_strategy_state": self._get_strategy_state,
            "get_tester_status": self._get_tester_status,
            "get_tester_results": self._get_tester_results,
            "compile_probe": self._compile_probe,
            "compile_trigger": self._compile_trigger,
        }
        handler = dispatch.get(action)
        if handler is None:
            return ExecutionResult(success=False, driver=self.name, stderr=f"Unknown action '{action}'")
        try:
            return handler(args)
        except urllib.error.URLError as exc:
            return ExecutionResult(
                success=False, driver=self.name,
                stderr=f"Connection to NT8 AddOn failed ({self.base_url}): {exc.reason}",
            )
        except Exception as exc:
            return ExecutionResult(success=False, driver=self.name, stderr=str(exc))

    # ── HTTP helpers ───────────────────────────────────────────────────

    def _get(self, path: str, **params) -> Any:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = resp.read()
            if resp.headers.get("Content-Type", "").startswith("image/"):
                return data
            return json.loads(data) if data else {}

    def _post(self, path: str, body: dict | None = None) -> Any:
        url = self.base_url + path
        payload = json.dumps(body or {}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = resp.read()
            return json.loads(data) if data else {}

    def _get_binary(self, path: str) -> bytes:
        url = self.base_url + path
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read()

    # ── actions ────────────────────────────────────────────────────────

    def _health(self, args: dict) -> ExecutionResult:
        data = self._get("/health")
        return ExecutionResult(
            success=data.get("ok", False),
            driver=self.name,
            stdout=json.dumps(data, indent=2),
            metadata=data,
        )

    def _get_version(self, args: dict) -> ExecutionResult:
        data = self._get("/version")
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=json.dumps(data, indent=2),
            metadata=data,
        )

    def _get_charts(self, args: dict) -> ExecutionResult:
        data = self._get("/charts")
        charts = data if isinstance(data, list) else data.get("charts", [])
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Found {len(charts)} charts",
            metadata={"charts": charts},
        )

    def _get_indicators(self, args: dict) -> ExecutionResult:
        chart_id = args.get("chart_id", "active")
        data = self._get(f"/chart/{chart_id}/indicators")
        indicators = data if isinstance(data, list) else data.get("indicators", [])
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Found {len(indicators)} indicators on chart {chart_id}",
            metadata={"indicators": indicators},
        )

    def _add_indicator(self, args: dict) -> ExecutionResult:
        chart_id = args.get("chart_id", "active")
        indicator_name = args.get("indicator", args.get("indicator_name", ""))
        body = {"name": indicator_name}
        if "parameters" in args:
            body["parameters"] = args["parameters"]
        data = self._post(f"/chart/{chart_id}/indicator/add", body)
        ok = data.get("ok", False)
        return ExecutionResult(
            success=ok, driver=self.name,
            stdout=f"Added indicator '{indicator_name}' to chart {chart_id}" if ok else data.get("error", "Failed"),
            metadata=data,
        )

    def _remove_indicator(self, args: dict) -> ExecutionResult:
        chart_id = args.get("chart_id", "active")
        body = {"name": args.get("indicator", args.get("indicator_name", ""))}
        if "index" in args:
            body["index"] = args["index"]
        data = self._post(f"/chart/{chart_id}/indicator/remove", body)
        ok = data.get("ok", False)
        return ExecutionResult(
            success=ok, driver=self.name,
            stdout=f"Removed indicator from chart {chart_id}" if ok else data.get("error", "Failed"),
            metadata=data,
        )

    def _screenshot(self, args: dict) -> ExecutionResult:
        chart_id = args.get("chart_id", "active")
        png_bytes = self._get_binary(f"/chart/{chart_id}/screenshot")
        self._captures_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        filename = f"chart_{chart_id}_{ts}.png"
        out_path = self._captures_dir / filename
        out_path.write_bytes(png_bytes)
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Saved screenshot to {out_path}",
            artifacts=[str(out_path)],
            metadata={"path": str(out_path), "size": len(png_bytes)},
        )

    def _get_accounts(self, args: dict) -> ExecutionResult:
        data = self._get("/accounts")
        accounts = data if isinstance(data, list) else data.get("accounts", [])
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Found {len(accounts)} accounts",
            metadata={"accounts": accounts},
        )

    def _get_account_info(self, args: dict) -> ExecutionResult:
        account = args["account"]
        data = self._get(f"/account/{urllib.parse.quote(account, safe='')}/state")
        ok = "error" not in data if isinstance(data, dict) else True
        return ExecutionResult(
            success=ok, driver=self.name,
            stdout=json.dumps(data, indent=2) if ok else data.get("error", "Failed"),
            metadata=data,
        )

    def _get_positions(self, args: dict) -> ExecutionResult:
        data = self._get("/positions")
        positions = data if isinstance(data, list) else data.get("positions", [])
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Found {len(positions)} positions",
            metadata={"positions": positions},
        )

    def _get_orders(self, args: dict) -> ExecutionResult:
        data = self._get("/orders")
        orders = data if isinstance(data, list) else data.get("orders", [])
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Found {len(orders)} orders",
            metadata={"orders": orders},
        )

    def _get_strategies(self, args: dict) -> ExecutionResult:
        data = self._get("/strategies")
        strategies = data if isinstance(data, list) else data.get("strategies", [])
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Found {len(strategies)} strategies",
            metadata={"strategies": strategies},
        )

    def _get_market_data(self, args: dict) -> ExecutionResult:
        instrument = args["instrument"]
        data = self._get(f"/market-data/{urllib.parse.quote(instrument, safe='')}")
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=json.dumps(data, indent=2),
            metadata=data,
        )

    def _subscribe_market_data(self, args: dict) -> ExecutionResult:
        instrument = args.get("instrument", args.get("symbol", ""))
        if not instrument:
            return ExecutionResult(success=False, driver=self.name, stderr="Missing 'instrument' arg")
        data = self._post("/market-data/subscribe", {"instrument": instrument})
        ok = data.get("ok", False)
        return ExecutionResult(
            success=ok, driver=self.name,
            stdout=f"Subscribed to market data for {instrument}" if ok else data.get("error", "Failed"),
            metadata=data,
        )

    def _unsubscribe_market_data(self, args: dict) -> ExecutionResult:
        instrument = args.get("instrument", args.get("symbol", ""))
        if not instrument:
            return ExecutionResult(success=False, driver=self.name, stderr="Missing 'instrument' arg")
        data = self._post("/market-data/unsubscribe", {"instrument": instrument})
        ok = data.get("ok", False)
        return ExecutionResult(
            success=ok, driver=self.name,
            stdout=f"Unsubscribed from market data for {instrument}" if ok else data.get("error", "Failed"),
            metadata=data,
        )

    def _historical_bars(self, args: dict) -> ExecutionResult:
        body = {
            "instrument": args["instrument"],
            "period_type": args.get("period_type", "Minute"),
            "period_value": args.get("period_value", 1),
            "bars_back": args.get("bars_back", 100),
        }
        if "from" in args:
            body["from"] = args["from"]
        if "to" in args:
            body["to"] = args["to"]
        data = self._post("/market-data/history", body)
        bars = data if isinstance(data, list) else data.get("bars", [])
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Retrieved {len(bars)} bars for {args['instrument']}",
            metadata={"bars": bars},
        )

    def _get_connections(self, args: dict) -> ExecutionResult:
        data = self._get("/connections")
        connections = data if isinstance(data, list) else data.get("connections", [])
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Found {len(connections)} connections",
            metadata={"connections": connections},
        )

    def _get_output_log(self, args: dict) -> ExecutionResult:
        data = self._get("/logs/output")
        text = data.get("text", "") if isinstance(data, dict) else str(data)
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=text,
            metadata={"text": text},
        )

    def _close_chart(self, args: dict) -> ExecutionResult:
        chart_id = args.get("chart_id", "active")
        data = self._post(f"/chart/{chart_id}/close", {})
        return ExecutionResult(success=data.get("ok", False), driver=self.name, metadata=data)

    def _save_template(self, args: dict) -> ExecutionResult:
        chart_id = args.get("chart_id", "active")
        name = args.get("name", "")
        data = self._post(f"/chart/{chart_id}/template/save", {"name": name})
        return ExecutionResult(success=data.get("ok", False), driver=self.name, metadata=data)

    def _apply_template(self, args: dict) -> ExecutionResult:
        chart_id = args.get("chart_id", "active")
        name = args.get("name", "")
        data = self._post(f"/chart/{chart_id}/template/apply", {"name": name})
        return ExecutionResult(success=data.get("ok", False), driver=self.name, metadata=data)

    def _attach_strategy(self, args: dict) -> ExecutionResult:
        strategy = args.get("strategy", "")
        symbol = args.get("symbol", "")
        period = args.get("period", "")
        params = args.get("params", {})
        data = self._post("/strategy/attach", {"strategy": strategy, "symbol": symbol, "period": period, "params": params})
        return ExecutionResult(success=data.get("ok", False), driver=self.name, metadata=data)

    def _detach_strategy(self, args: dict) -> ExecutionResult:
        strategy = args.get("strategy", "")
        data = self._post("/strategy/detach", {"strategy": strategy})
        return ExecutionResult(success=data.get("ok", False), driver=self.name, metadata=data)

    def _get_strategy_state(self, args: dict) -> ExecutionResult:
        strategy = args.get("strategy", "")
        data = self._get(f"/strategy/{urllib.parse.quote(strategy, safe='')}/state")
        return ExecutionResult(success=True, driver=self.name, stdout=json.dumps(data, indent=2), metadata=data)

    def _get_tester_status(self, args: dict) -> ExecutionResult:
        data = self._get("/tester/status")
        return ExecutionResult(success=True, driver=self.name, stdout=json.dumps(data, indent=2), metadata=data)

    def _get_tester_results(self, args: dict) -> ExecutionResult:
        data = self._get("/tester/results")
        return ExecutionResult(success=True, driver=self.name, stdout=json.dumps(data, indent=2), metadata=data)

    def _compile_probe(self, args: dict) -> ExecutionResult:
        data = self._get("/compile/probe")
        candidates = data.get("candidates", []) if isinstance(data, dict) else []
        return ExecutionResult(
            success=True, driver=self.name,
            stdout=f"Found {len(candidates)} reflection candidates containing 'Compil'",
            metadata=data,
        )

    def _compile_trigger(self, args: dict) -> ExecutionResult:
        data = self._post("/compile/trigger", {})
        attempted = data.get("attempted", False) if isinstance(data, dict) else False
        return ExecutionResult(
            success=attempted, driver=self.name,
            stdout=json.dumps(data, indent=2),
            metadata=data,
        )
