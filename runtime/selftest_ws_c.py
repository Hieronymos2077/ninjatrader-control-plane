"""
WS-C self test: file_write.py new actions, dll_ati.py OIF line builder, keyboard.py
pure helpers, win32_capture.py pure helpers.

Runs entirely against a TEMP fake NT8 data dir built with tempfile. Never touches
C:\\Users\\<you>\\Documents\\NinjaTrader 8. Never sends real keystrokes. Never
launches or kills NinjaTrader.

Run with: .venv\\Scripts\\python.exe runtime\\selftest_ws_c.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from runtime.backends.file_write import FileWriteBackend
from runtime.backends.dll_ati import DllAtiBackend
from runtime.backends import keyboard as kb
from runtime.backends import win32_capture as w32

_results: list[tuple[str, str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    _results.append((name, status, detail))
    line = f"[{status}] {name}"
    if detail:
        line += f" :: {detail}"
    print(line)
    return condition


def utc_ts(y, mo, d, h, mi, s) -> float:
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc).timestamp()


def main() -> int:
    real_nt8_dir = Path.home() / "Documents" / "NinjaTrader 8"
    temp_root = Path(tempfile.mkdtemp(prefix="nt8_selftest_ws_c_"))
    assert real_nt8_dir not in temp_root.parents and temp_root != real_nt8_dir, "refusing to run against the real NT8 dir"
    print(f"Temp NT8 data dir: {temp_root}")

    try:
        _build_fixture(temp_root)
        _test_compile_status(temp_root)
        _test_parse_compile_errors(temp_root)
        _test_analyzer_status(temp_root)
        _test_analyzer_results(temp_root)
        _test_analyzer_list_results(temp_root)
        _test_path_traversal_guard(temp_root)
        _test_oif_line_builder(temp_root)
        _test_keyboard_pure_helpers()
        _test_win32_pure_helpers()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
        print(f"Cleaned up temp dir: {temp_root}")

    passed = sum(1 for _, s, _ in _results if s == "PASS")
    failed = sum(1 for _, s, _ in _results if s == "FAIL")
    print(f"\n==== SELFTEST SUMMARY: {passed} passed, {failed} failed, {len(_results)} total ====")
    return 1 if failed else 0


# ── fixture ──────────────────────────────────────────────────────────────

def _build_fixture(root: Path) -> None:
    dll_dir = root / "bin" / "Custom"
    dll_dir.mkdir(parents=True, exist_ok=True)
    (dll_dir / "NinjaTrader.Custom.dll").write_bytes(b"FAKE_DLL_CONTENT_V1")

    trace_dir = root / "trace"
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_lines = [
        "2026-07-11 09:00:00:000 NinjaScriptEditorHotKeys: Compile='F5'",
        "2026-07-11 09:15:20:000 Compiling and reloading NinjaTrader.Custom...",
        "2026-07-11 09:15:24:000 Unable to compile custom assembly. Original version has been restored.",
        "2026-07-11 09:15:25:000 MyStrategy.cs(45,10): error CS1002: ; expected",
        "2026-07-11 09:15:26:000 MyStrategy.cs(52,5): error CS0103: The name 'foo' does not exist in the current context",
        "2026-07-11 09:20:00:000 Some unrelated trace line without the keyword",
    ]
    (trace_dir / "trace.20260711.00000.txt").write_text("\n".join(trace_lines) + "\n", encoding="utf-8")

    log_dir = root / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_lines = [
        "2026-07-11 09:15:27:000 MyIndicator.cs(10,3): warning CS0219: The variable 'x' is assigned but its value is never used",
    ]
    (log_dir / "log.20260711.00000.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    sa_dir = root / "strategyanalyzerlogs"
    sa_dir.mkdir(parents=True, exist_ok=True)

    older_mystrategy = sa_dir / "MyStrategy_20260710_090000_01.xml"
    older_mystrategy.write_text(
        "<StrategyAnalyzerLog>"
        "<StrategyAnalyzerGridEntry>"
        "<Action>Backtest</Action>"
        "<Date>2026-07-10 09:00:00</Date>"
        "<Instrument>ES 09-25</Instrument>"
        "<From>2026-01-01</From>"
        "<StrategyFile>MyStrategy</StrategyFile>"
        "<SummaryPerformances Unit=\"Currency\">"
        "<PerformanceUnit>Currency</PerformanceUnit>"
        "<SummaryPerformancesSerialize>TotalNetProfit;100.00;60.00;40.00|ProfitFactor;1.10;1.12;1.05|"
        "TotalNumTrades;10;6;4|MaxDrawdown;-50.00;-30.00;-20.00</SummaryPerformancesSerialize>"
        "</SummaryPerformances>"
        "</StrategyAnalyzerGridEntry>"
        "</StrategyAnalyzerLog>",
        encoding="utf-8",
    )

    newest_mystrategy = sa_dir / "MyStrategy_20260711_093000_01.xml"
    newest_mystrategy.write_text(
        "<StrategyAnalyzerLog>"
        "<StrategyAnalyzerGridEntry>"
        "<Action>Backtest</Action>"
        "<Date>2026-07-11 09:30:00</Date>"
        "<Instrument>ES 09-25</Instrument>"
        "<From>2026-01-01</From>"
        "<Guid>abc-123-def-456</Guid>"
        "<StrategyFile>MyStrategy</StrategyFile>"
        "<OptimizationParameters>"
        "<Parameter Name=\"FastPeriod\" Value=\"9\" />"
        "<Parameter Name=\"SlowPeriod\" Value=\"21\" />"
        "</OptimizationParameters>"
        "<SummaryPerformances Unit=\"Currency\">"
        "<PerformanceUnit>Currency</PerformanceUnit>"
        "<SummaryPerformancesSerialize>TotalNetProfit;542.50;325.00;217.50|ProfitFactor;1.55;1.62;1.48|"
        "TotalNumTrades;42;25;17|MaxDrawdown;-118.75;-80.00;-58.75|SharpeRatio;1.21;1.15;1.05|"
        "PercentProfitable;54.76;56.00;52.94|NumWinningTrades;23;14;9|NumLosingTrades;19;11;8"
        "</SummaryPerformancesSerialize>"
        "</SummaryPerformances>"
        "<SummaryPerformances Unit=\"Percent\">"
        "<PerformanceUnit>Percent</PerformanceUnit>"
        "<SummaryPerformancesSerialize>TotalNetProfit;5.42;3.25;2.17|ProfitFactor;1.55;1.62;1.48</SummaryPerformancesSerialize>"
        "</SummaryPerformances>"
        "</StrategyAnalyzerGridEntry>"
        "</StrategyAnalyzerLog>",
        encoding="utf-8",
    )

    other_strategy = sa_dir / "OtherStrategy_20260711_094500_01.xml"
    other_strategy.write_text(
        "<StrategyAnalyzerLog>"
        "<StrategyAnalyzerGridEntry>"
        "<Action>Backtest</Action>"
        "<Date>2026-07-11 09:45:00</Date>"
        "<Instrument>NQ 09-25</Instrument>"
        "<From>2026-02-01</From>"
        "<StrategyFile>OtherStrategy</StrategyFile>"
        "<SummaryPerformances Unit=\"Currency\">"
        "<PerformanceUnit>Currency</PerformanceUnit>"
        "<SummaryPerformancesSerialize>TotalNetProfit;-25.00;-10.00;-15.00|ProfitFactor;0.85;0.90;0.80|"
        "TotalNumTrades;8;4;4|MaxDrawdown;-75.00;-40.00;-35.00</SummaryPerformancesSerialize>"
        "</SummaryPerformances>"
        "</StrategyAnalyzerGridEntry>"
        "</StrategyAnalyzerLog>",
        encoding="utf-8",
    )

    import os as _os
    ts_older = utc_ts(2026, 7, 10, 9, 0, 0)
    ts_newest = utc_ts(2026, 7, 11, 9, 30, 0)
    ts_other = utc_ts(2026, 7, 11, 9, 45, 0)
    _os.utime(older_mystrategy, (ts_older, ts_older))
    _os.utime(newest_mystrategy, (ts_newest, ts_newest))
    _os.utime(other_strategy, (ts_other, ts_other))

    global OLDER_MYSTRATEGY_NAME
    OLDER_MYSTRATEGY_NAME = older_mystrategy.name


OLDER_MYSTRATEGY_NAME = ""


# ── file_write.py tests ────────────────────────────────────────────────

def _test_compile_status(root: Path) -> None:
    print("\n-- compile_status --")
    backend = FileWriteBackend(nt8_data_dir=root)
    result = backend.execute("compile_status", {})
    check("compile_status success", result.success, result.stderr)
    md = result.metadata
    check("compile_status exists=True", md.get("exists") is True, str(md))
    check("compile_status dll_path correct", md.get("dll_path") == str(root / "bin" / "Custom" / "NinjaTrader.Custom.dll"))
    check("compile_status size matches fixture", md.get("size") == len(b"FAKE_DLL_CONTENT_V1"), str(md.get("size")))
    check("compile_status mtime_iso present", bool(md.get("mtime_iso")))
    trace_lines = md.get("trace_lines", [])
    # Note: "Compiling" does not contain the substring "compile" (it has
    # "compili...", not "compile"), so only the 2 lines with the literal
    # substring "compile" match: "Compile='F5'" and "Unable to compile".
    check("compile_status trace_lines count == 2", len(trace_lines) == 2, str(trace_lines))
    check(
        "compile_status trace_lines contain failure marker",
        any("unable to compile" in l.lower() for l in trace_lines),
        str(trace_lines),
    )


def _test_parse_compile_errors(root: Path) -> None:
    print("\n-- parse_compile_errors --")
    backend = FileWriteBackend(nt8_data_dir=root)

    result = backend.execute("parse_compile_errors", {})
    check("parse_compile_errors (no since) success", result.success, result.stderr)
    md = result.metadata
    check("parse_compile_errors found_failure_marker True", md.get("found_failure_marker") is True)
    errors = md.get("errors", [])
    check("parse_compile_errors errors count == 4", len(errors) == 4, str(errors))
    structured = [e for e in errors if "code" in e]
    raw = [e for e in errors if "raw" in e]
    check("parse_compile_errors has 1 raw entry", len(raw) == 1, str(raw))
    check("parse_compile_errors has 3 structured entries", len(structured) == 3, str(structured))
    codes = sorted(e["code"] for e in structured)
    check("parse_compile_errors codes match", codes == ["CS0103", "CS0219", "CS1002"], str(codes))
    cs1002 = next((e for e in structured if e["code"] == "CS1002"), None)
    check(
        "parse_compile_errors CS1002 file/line correct",
        cs1002 is not None and cs1002["file"] == "MyStrategy.cs" and cs1002["line"] == 45,
        str(cs1002),
    )

    result_since = backend.execute("parse_compile_errors", {"since": "2026-07-11T09:25:00"})
    check("parse_compile_errors (since after all) success", result_since.success, result_since.stderr)
    md_since = result_since.metadata
    check("parse_compile_errors (since) found_failure_marker False", md_since.get("found_failure_marker") is False)
    check("parse_compile_errors (since) errors empty", md_since.get("errors") == [], str(md_since.get("errors")))


def _test_analyzer_status(root: Path) -> None:
    print("\n-- analyzer_status --")
    backend = FileWriteBackend(nt8_data_dir=root)

    result = backend.execute("analyzer_status", {})
    check("analyzer_status (no filter) success", result.success, result.stderr)
    md = result.metadata
    check("analyzer_status found True", md.get("found") is True)
    entries = md.get("entries", [])
    check("analyzer_status 3 entries", len(entries) == 3, str(entries))
    check(
        "analyzer_status newest-first order",
        [e["name"] for e in entries] == [
            "OtherStrategy_20260711_094500_01.xml",
            "MyStrategy_20260711_093000_01.xml",
            OLDER_MYSTRATEGY_NAME,
        ],
        str([e["name"] for e in entries]),
    )
    check(
        "analyzer_status strategy_guess values",
        [e["strategy_guess"] for e in entries] == ["OtherStrategy", "MyStrategy", "MyStrategy"],
        str([e["strategy_guess"] for e in entries]),
    )

    result_filtered = backend.execute("analyzer_status", {"strategy": "MyStrategy"})
    entries_f = result_filtered.metadata.get("entries", [])
    check("analyzer_status strategy filter -> 2 entries", len(entries_f) == 2, str(entries_f))

    result_no_match = backend.execute("analyzer_status", {"strategy": "NoSuchStrategy"})
    check("analyzer_status no-match filter -> found False", result_no_match.metadata.get("found") is False)
    check("analyzer_status no-match filter -> 0 entries", result_no_match.metadata.get("entries") == [])

    result_since_true = backend.execute("analyzer_status", {"since": "2026-07-11T09:40:00"})
    check("analyzer_status since (before newest) -> found True", result_since_true.metadata.get("found") is True)

    result_since_false = backend.execute("analyzer_status", {"since": "2026-07-11T10:00:00"})
    check("analyzer_status since (after newest) -> found False", result_since_false.metadata.get("found") is False)


def _test_analyzer_results(root: Path) -> None:
    print("\n-- analyzer_results --")
    backend = FileWriteBackend(nt8_data_dir=root)

    result_newest_overall = backend.execute("analyzer_results", {})
    check("analyzer_results (no filter) success", result_newest_overall.success, result_newest_overall.stderr)
    md = result_newest_overall.metadata
    check("analyzer_results (no filter) picks OtherStrategy (newest overall)", md.get("strategy_file") == "OtherStrategy", str(md))
    check("analyzer_results (no filter) instrument", md.get("instrument") == "NQ 09-25")
    other_currency = md.get("performance", {}).get("Currency", {})
    check(
        "analyzer_results (no filter) TotalNetProfit all=-25.00",
        other_currency.get("TotalNetProfit") == {"all": "-25.00", "long": "-10.00", "short": "-15.00"},
        str(other_currency.get("TotalNetProfit")),
    )

    result_mystrategy = backend.execute("analyzer_results", {"strategy": "MyStrategy"})
    check("analyzer_results (strategy=MyStrategy) success", result_mystrategy.success, result_mystrategy.stderr)
    md2 = result_mystrategy.metadata
    check("analyzer_results (strategy) picks newest MyStrategy xml", md2.get("date") == "2026-07-11 09:30:00", str(md2))
    check("analyzer_results (strategy) action", md2.get("action") == "Backtest")
    check("analyzer_results (strategy) instrument", md2.get("instrument") == "ES 09-25")
    check("analyzer_results (strategy) from_date", md2.get("from_date") == "2026-01-01")
    check(
        "analyzer_results (strategy) parameters",
        md2.get("parameters") == {"FastPeriod": "9", "SlowPeriod": "21"},
        str(md2.get("parameters")),
    )
    currency = md2.get("performance", {}).get("Currency", {})
    check(
        "analyzer_results (strategy) TotalNetProfit all/long/short",
        currency.get("TotalNetProfit") == {"all": "542.50", "long": "325.00", "short": "217.50"},
        str(currency.get("TotalNetProfit")),
    )
    check(
        "analyzer_results (strategy) ProfitFactor",
        currency.get("ProfitFactor") == {"all": "1.55", "long": "1.62", "short": "1.48"},
        str(currency.get("ProfitFactor")),
    )
    check(
        "analyzer_results (strategy) MaxDrawdown",
        currency.get("MaxDrawdown") == {"all": "-118.75", "long": "-80.00", "short": "-58.75"},
        str(currency.get("MaxDrawdown")),
    )
    percent = md2.get("performance", {}).get("Percent", {})
    check(
        "analyzer_results (strategy) Percent block present",
        percent.get("TotalNetProfit") == {"all": "5.42", "long": "3.25", "short": "2.17"},
        str(percent),
    )

    result_by_name = backend.execute("analyzer_results", {"name": OLDER_MYSTRATEGY_NAME})
    check("analyzer_results (by exact name) success", result_by_name.success, result_by_name.stderr)
    md3 = result_by_name.metadata
    check(
        "analyzer_results (by exact name) TotalNetProfit all=100.00",
        md3.get("performance", {}).get("Currency", {}).get("TotalNetProfit", {}).get("all") == "100.00",
        str(md3.get("performance")),
    )

    result_missing = backend.execute("analyzer_results", {"name": "does_not_exist.xml"})
    check("analyzer_results (missing name) success=False", result_missing.success is False)
    check(
        "analyzer_results (missing name) error_code",
        result_missing.metadata.get("error_code") == "ANALYZER_RESULTS_NOT_FOUND",
        str(result_missing.metadata),
    )


def _test_analyzer_list_results(root: Path) -> None:
    print("\n-- analyzer_list_results --")
    backend = FileWriteBackend(nt8_data_dir=root)

    result = backend.execute("analyzer_list_results", {"limit": 10})
    check("analyzer_list_results success", result.success, result.stderr)
    results = result.metadata.get("results", [])
    check("analyzer_list_results 3 results", len(results) == 3, str(results))
    check(
        "analyzer_list_results newest-first order",
        [r["name"] for r in results] == [
            "OtherStrategy_20260711_094500_01.xml",
            "MyStrategy_20260711_093000_01.xml",
            OLDER_MYSTRATEGY_NAME,
        ],
        str([r["name"] for r in results]),
    )
    top = results[0]
    check(
        "analyzer_list_results headline stats for newest",
        top.get("TotalNetProfit") == "-25.00"
        and top.get("ProfitFactor") == "0.85"
        and top.get("TotalNumTrades") == "8"
        and top.get("MaxDrawdown") == "-75.00",
        str(top),
    )

    result_limited = backend.execute("analyzer_list_results", {"strategy": "MyStrategy", "limit": 1})
    results_limited = result_limited.metadata.get("results", [])
    check("analyzer_list_results strategy+limit -> 1 result", len(results_limited) == 1, str(results_limited))
    check(
        "analyzer_list_results strategy+limit -> correct entry",
        results_limited and results_limited[0]["name"] == "MyStrategy_20260711_093000_01.xml"
        and results_limited[0]["TotalNetProfit"] == "542.50",
        str(results_limited),
    )


def _test_path_traversal_guard(root: Path) -> None:
    print("\n-- path traversal guard --")
    backend = FileWriteBackend(nt8_data_dir=root)
    result = backend.execute("write_file", {"name": "../../evil", "content": "x", "type": "strategy"})
    check("write_file with .. in name is rejected", result.success is False, result.stderr)
    result2 = backend.execute("write_file", {"name": "sub/evil", "content": "x", "type": "strategy"})
    check("write_file with path separator in name is rejected", result2.success is False, result2.stderr)
    escaped = list((root / "bin" / "Custom").parent.glob("evil*"))
    check("no file escaped bin/Custom", escaped == [], str(escaped))


# ── dll_ati.py tests ────────────────────────────────────────────────────

def _test_oif_line_builder(root: Path) -> None:
    print("\n-- dll_ati OIF line builder --")
    backend = DllAtiBackend(nt8_data_dir=root)
    result = backend.execute("place_order", {
        "account": "Sim101",
        "instrument": "6E 03-21",
        "action": "SELL",
        "qty": "1",
        "order_type": "MARKET",
        "tif": "GTC",
    })
    check("place_order success", result.success, result.stderr)
    expected_line = "PLACE;Sim101;6E 03-21;SELL;1;MARKET;;;GTC;;;;"
    actual_line = result.metadata.get("command")
    check("OIF PLACE line matches CONTRACT format exactly", actual_line == expected_line, f"got: {actual_line!r}")
    oif_path = Path(result.metadata["oif_file"])
    check("OIF file was written under incoming/", oif_path.parent == root / "incoming")
    check("OIF file content matches line", oif_path.read_text(encoding="utf-8") == expected_line)

    not_supported = backend.execute("get_market_data", {"instrument": "ES 09-25"})
    check("get_market_data not supported via file", not_supported.success is False)
    check(
        "get_market_data message points to addon_http",
        "addon_http" in not_supported.stderr and not_supported.metadata.get("suggestion") == "addon_http",
        not_supported.stderr,
    )


# ── keyboard.py pure helper tests (no win32 calls) ──────────────────────

def _test_keyboard_pure_helpers() -> None:
    print("\n-- keyboard pure helpers --")

    windows = [
        (1, "NinjaTrader - Control Center"),
        (2, "ES 09-25, 5 Min (Chart)"),
        (3, "NinjaScript Editor - MyStrategy.cs"),
        (4, "Strategy Analyzer"),
    ]

    check(
        "_match_window_by_title finds NinjaScript Editor",
        kb._match_window_by_title(windows, "NinjaScript Editor") == (3, "NinjaScript Editor - MyStrategy.cs"),
    )
    check(
        "_match_window_by_title is case insensitive",
        kb._match_window_by_title(windows, "strategy analyzer") == (4, "Strategy Analyzer"),
    )
    check("_match_window_by_title no match -> None", kb._match_window_by_title(windows, "Does Not Exist") is None)
    check("_match_window_by_title empty list -> None", kb._match_window_by_title([], "Anything") is None)
    check("_match_window_by_title no filter -> first window", kb._match_window_by_title(windows, None) == windows[0])

    check("_is_chart_title rejects Control Center", kb._is_chart_title("NinjaTrader - Control Center") is False)
    check("_is_chart_title rejects NinjaScript Editor", kb._is_chart_title("NinjaScript Editor - Foo.cs") is False)
    check("_is_chart_title rejects Strategy Analyzer", kb._is_chart_title("Strategy Analyzer") is False)
    check("_is_chart_title accepts chart window", kb._is_chart_title("ES 09-25, 5 Min (Chart)") is True)

    check(
        "_pick_chart_window picks first non-CC/non-Editor window",
        kb._pick_chart_window(windows, None) == (2, "ES 09-25, 5 Min (Chart)"),
    )
    check(
        "_pick_chart_window honors explicit title_contains",
        kb._pick_chart_window(windows, "MyStrategy") == (3, "NinjaScript Editor - MyStrategy.cs"),
    )

    resolved = kb._substitute_placeholders("{strategy} test {instrument} end", {"strategy": "MyStrat", "instrument": ""})
    check("_substitute_placeholders fills present value and empties missing", resolved == "MyStrat test  end", resolved)
    resolved2 = kb._substitute_placeholders("no placeholders here", {"strategy": "X"})
    check("_substitute_placeholders passes through plain text", resolved2 == "no placeholders here", resolved2)

    default_steps = kb._normalize_steps(None, kb.TESTER_CONFIG_STEPS)
    check("_normalize_steps(None) returns default TESTER_CONFIG_STEPS", default_steps == kb.TESTER_CONFIG_STEPS)

    custom = [{"keys": "tab"}, {"text": "{strategy}"}, {"wait_ms": 100}]
    normalized_custom = kb._normalize_steps(custom, kb.TESTER_CONFIG_STEPS)
    check("_normalize_steps(custom) returns the custom list unchanged", normalized_custom == custom)

    threw = False
    try:
        kb._normalize_steps([{"bogus": 1}], kb.TESTER_CONFIG_STEPS)
    except ValueError:
        threw = True
    check("_normalize_steps rejects a step with no recognized key", threw)

    threw2 = False
    try:
        kb._normalize_steps([123], kb.TESTER_CONFIG_STEPS)
    except ValueError:
        threw2 = True
    check("_normalize_steps rejects a non-dict step", threw2)

    check(
        "TESTER_CONFIG_STEPS is a non-empty list of dicts",
        isinstance(kb.TESTER_CONFIG_STEPS, list) and len(kb.TESTER_CONFIG_STEPS) > 0
        and all(isinstance(s, dict) for s in kb.TESTER_CONFIG_STEPS),
        str(kb.TESTER_CONFIG_STEPS),
    )


def _test_win32_pure_helpers() -> None:
    print("\n-- win32_capture pure helpers --")

    width, height = 4, 4
    solid = b"\x10\x20\x30\xff" * (width * height)
    ratio_solid = w32._sample_blank_ratio(solid, width, height, sample_stride=1)
    check("_sample_blank_ratio solid image -> ratio 1.0", ratio_solid == 1.0, str(ratio_solid))

    varied = bytearray()
    for i in range(width * height):
        varied += bytes([i % 256, (i * 7) % 256, (i * 13) % 256, 0xff])
    ratio_varied = w32._sample_blank_ratio(bytes(varied), width, height, sample_stride=1)
    check("_sample_blank_ratio varied image -> ratio < 1.0", ratio_varied < 1.0, str(ratio_varied))

    ratio_empty = w32._sample_blank_ratio(b"", 0, 0)
    check("_sample_blank_ratio zero-size image -> ratio 0.0", ratio_empty == 0.0)


if __name__ == "__main__":
    sys.exit(main())
