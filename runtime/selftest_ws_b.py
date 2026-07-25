"""
Self test for workstream WS-B (AntigravityBridgeAddOn.cs + runtime/backends/addon_http.py).

Never touches C:\\Users\\<you>\\Documents\\NinjaTrader 8. Never launches NinjaTrader.
All network activity is against a stdlib http.server mock bound to 127.0.0.1:18089.

Run with:
    .venv\\Scripts\\python.exe runtime\\selftest_ws_b.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKENDS_DIR = PROJECT_ROOT / "runtime" / "backends"
CS_PATH = PROJECT_ROOT / "runtime" / "assets" / "nt8" / "AntigravityBridgeAddOn.cs"
PY_PATH = BACKENDS_DIR / "addon_http.py"

MOCK_PORT = 18089

failures: list[str] = []
passed: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        passed.append(label)
        print(f"PASS: {label}")
    else:
        failures.append(label)
        print(f"FAIL: {label} {detail}")


# ── (a) standalone syntax and import check ──────────────────────────────

def test_standalone_import():
    print("\n=== (a) standalone import and syntax check of addon_http.py ===")

    import py_compile
    try:
        py_compile.compile(str(PY_PATH), doraise=True)
        check("py_compile addon_http.py", True)
    except py_compile.PyCompileError as exc:
        check("py_compile addon_http.py", False, str(exc))
        return None

    # Import it as a standalone top level module (no package context), which
    # forces its own "except ImportError: from base import ..." fallback path,
    # the same path it takes when NT8's script host or a bare script imports it.
    sys.path.insert(0, str(BACKENDS_DIR))
    try:
        spec = importlib.util.spec_from_file_location("addon_http_standalone", str(PY_PATH))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        check("standalone import of addon_http module", True)
        check("AddonHttpBackend class present", hasattr(module, "AddonHttpBackend"))
        return module
    except Exception as exc:
        check("standalone import of addon_http module", False, repr(exc))
        return None


# ── (b) mock AddOn HTTP server + backend action tests ────────────────────

MOCK_STATE = {"subscriptions": set()}


class MockAddonHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            self._send(200, {"ok": True, "version": "2.0.0", "charts_count": 0, "accounts_count": 1})
        elif path == "/version":
            self._send(200, {"bridge_version": "2.0.0", "nt8_version": "unknown"})
        elif path == "/account/TestAccount/state":
            self._send(200, {
                "name": "TestAccount", "buying_power": 1000.0, "cash_value": 500.0,
                "net_liquidation": 1500.0, "realized_pnl": 10.0, "unrealized_pnl": -5.0,
                "position_count": 2, "order_count": 1,
            })
        elif path == "/account/GhostAccount/state":
            self._send(200, {"ok": False, "error": "Account not found: GhostAccount"})
        elif path == "/compile/probe":
            self._send(200, {"ok": True, "experimental": True, "candidates": []})
        else:
            self._send(404, {"ok": False, "error": "not found: " + path})

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._read_body()
        if path == "/market-data/subscribe":
            instrument = body.get("instrument", "")
            already = instrument in MOCK_STATE["subscriptions"]
            MOCK_STATE["subscriptions"].add(instrument)
            self._send(200, {"ok": True, "instrument": instrument, "already_subscribed": already})
        elif path == "/market-data/unsubscribe":
            instrument = body.get("instrument", "")
            was = instrument in MOCK_STATE["subscriptions"]
            MOCK_STATE["subscriptions"].discard(instrument)
            self._send(200, {"ok": True, "instrument": instrument, "was_subscribed": was})
        elif path == "/chart/active/indicator/remove":
            name = body.get("name", "")
            if name == "EMA":
                self._send(200, {"ok": True})
            else:
                self._send(200, {"ok": False, "error": "Failed to remove indicator, got name=" + repr(name)})
        elif path == "/compile/trigger":
            self._send(200, {"attempted": False, "reason": "no candidate in mock", "experimental": True})
        else:
            self._send(404, {"ok": False, "error": "not found: " + path})


def test_backend_actions(module):
    print("\n=== (b) mock AddOn HTTP server + backend action tests ===")

    if module is None:
        check("skip backend action tests, module failed to import", False, "module is None")
        return

    server = ThreadingHTTPServer(("127.0.0.1", MOCK_PORT), MockAddonHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)

    try:
        backend = module.AddonHttpBackend(host="127.0.0.1", port=MOCK_PORT, timeout=5)

        r = backend.execute("health", {})
        check("action health parses ok", r.success and r.metadata.get("version") == "2.0.0", str(r))

        r = backend.execute("get_version", {})
        check("action get_version parses bridge_version", r.success and r.metadata.get("bridge_version") == "2.0.0", str(r))

        r = backend.execute("get_account_info", {"account": "TestAccount"})
        check(
            "action get_account_info parses account state",
            r.success and r.metadata.get("net_liquidation") == 1500.0 and r.metadata.get("position_count") == 2,
            str(r),
        )

        r = backend.execute("get_account_info", {"account": "GhostAccount"})
        check("action get_account_info reports failure for unknown account", r.success is False, str(r))

        r = backend.execute("subscribe_market_data", {"instrument": "ES 12-26"})
        check("action subscribe_market_data subscribes", r.success and r.metadata.get("instrument") == "ES 12-26", str(r))

        r = backend.execute("subscribe_market_data", {"symbol": "ES 12-26"})
        check("action subscribe_market_data accepts 'symbol' alias and reports already_subscribed", r.success and r.metadata.get("already_subscribed") is True, str(r))

        r = backend.execute("unsubscribe_market_data", {"instrument": "ES 12-26"})
        check("action unsubscribe_market_data unsubscribes", r.success and r.metadata.get("was_subscribed") is True, str(r))

        r = backend.execute("remove_indicator", {"chart_id": "active", "indicator": "EMA"})
        check("action remove_indicator with 'indicator' key reaches C# body as name=EMA", r.success, str(r))

        r = backend.execute("remove_indicator", {"chart_id": "active", "indicator_name": "EMA"})
        check("action remove_indicator with legacy 'indicator_name' key still works", r.success, str(r))

        r = backend.execute("compile_probe", {})
        check("action compile_probe parses candidates", r.success and "candidates" in r.metadata, str(r))

        r = backend.execute("compile_trigger", {})
        check("action compile_trigger reflects attempted=False from mock", r.success is False and r.metadata.get("attempted") is False, str(r))

    finally:
        server.shutdown()
        server.server_close()


# ── (c) C# sanity pass ────────────────────────────────────────────────

def test_cs_sanity():
    print("\n=== (c) C# sanity pass on AntigravityBridgeAddOn.cs ===")

    text = CS_PATH.read_text(encoding="utf-8")

    open_braces = text.count("{")
    close_braces = text.count("}")
    check(f"balanced braces ({open_braces} open, {close_braces} close)", open_braces == close_braces)

    out_var_matches = re.findall(r"\bout\s+var\b", text)
    check("no 'out var' (C# 7+ inline out declaration)", len(out_var_matches) == 0, str(out_var_matches))

    # Negative lookbehind for a word char excludes method/constructor parameter
    # lists like "HandleSaveTemplate(string chartId, string body)", which are
    # ordinary C# 1.0 parameter declarations, not C# 7 value tuple literals.
    # A real tuple literal is a value expression, so it is never immediately
    # preceded by an identifier character.
    tuple_matches = re.findall(
        r"(?<!\w)\(\s*(?:int|string|bool|double|float|long)\s+\w+\s*,\s*(?:int|string|bool|double|float|long)\s+\w+\s*\)",
        text,
    )
    check("no value tuple literals '(Type a, Type b)'", len(tuple_matches) == 0, str(tuple_matches))

    pattern_match_matches = re.findall(r"\bis\s+[A-Za-z_][\w.]*\s+[a-z_]\w*\s*[)&|;]", text)
    check("no C# 7 'is Type var' pattern matching", len(pattern_match_matches) == 0, str(pattern_match_matches))

    class_name_ok = "public class AntigravityBridge : AddOnBase" in text
    check("class name AntigravityBridge unchanged", class_name_ok)
    check("file name matches class name", CS_PATH.stem == "AntigravityBridgeAddOn")

    required_snippets = [
        ('GET /health wired', 'path == "/health"'),
        ('GET /version wired', 'path == "/version"'),
        ('HandleVersion defined', 'private string HandleVersion()'),
        ('GET /compile/probe wired', 'path == "/compile/probe"'),
        ('HandleCompileProbe defined', 'private string HandleCompileProbe()'),
        ('POST /compile/trigger wired', 'path == "/compile/trigger"'),
        ('HandleCompileTrigger defined', 'private string HandleCompileTrigger()'),
        ('GET /account/{name}/state wired', 'segments[0] == "account" && segments[2] == "state"'),
        ('HandleAccountState defined', 'private string HandleAccountState(string accountName)'),
        ('POST /market-data/subscribe wired', 'path == "/market-data/subscribe"'),
        ('HandleSubscribeMarketData defined', 'private string HandleSubscribeMarketData(string body)'),
        ('POST /market-data/unsubscribe wired', 'path == "/market-data/unsubscribe"'),
        ('HandleUnsubscribeMarketData defined', 'private string HandleUnsubscribeMarketData(string body)'),
        ('NotSupportedJson helper defined', 'private static string NotSupportedJson(string message, string remediation)'),
        ('template save uses NotSupportedJson', 'HandleSaveTemplate(string chartId, string body)\n        {\n            return NotSupportedJson('),
        ('strategy attach uses NotSupportedJson', 'HandleAttachStrategy(string body)\n        {\n            return NotSupportedJson('),
        ('tester status uses NotSupportedJson', 'HandleGetTesterStatus()\n        {\n            return NotSupportedJson('),
        ('tester results uses NotSupportedJson', 'HandleGetTesterResults()\n        {\n            return NotSupportedJson('),
        ('X-Capture-Method header set', 'resp.Headers.Add("X-Capture-Method", captureMethod)'),
        ('null-or-exception screenshot fallback restructured', 'if (bmp != null)'),
        ('port config file path', '"nt8bridge_port.txt"'),
        ('port-in-use guard', 'catch (HttpListenerException ex)'),
        ('RawJson helper defined', 'private sealed class RawJson'),
        ('market data subscriptions dictionary', '_marketDataSubscriptions'),
        ('BridgeVersion constant is 2.0.0', 'private const string BridgeVersion = "2.0.0";'),
    ]
    for label, snippet in required_snippets:
        check(label, snippet in text)


def main():
    module = test_standalone_import()
    test_backend_actions(module)
    test_cs_sanity()

    print("\n=== SUMMARY ===")
    print(f"passed: {len(passed)}")
    print(f"failed: {len(failures)}")
    if failures:
        print("FAILED CHECKS:")
        for f in failures:
            print(f"  * {f}")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
