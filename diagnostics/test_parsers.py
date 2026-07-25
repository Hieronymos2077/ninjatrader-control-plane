"""Fixture based tests for the file_write analyzer and compile parsers.

CONTRACT.md adds five new file_write actions that WS-C is landing in parallel:
compile_status, parse_compile_errors, analyzer_status, analyzer_results,
analyzer_list_results. Until they land, FileWriteBackend.execute returns a
clean "Unknown action" failure for them, which this suite treats as WARN, not
FAIL. Once an action exists, this suite calls it against TEMP fixtures built
to the exact strategyanalyzerlogs XML schema and trace failure marker line
documented in CONTRACT.md's empirical facts, and checks the fixture's known
numbers or markers show up in the response.

Run directly:
    python diagnostics\\test_parsers.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import Result, cleanup_temp_dir, dump_text, make_temp_nt8_dir, report  # noqa: E402


ANALYZER_XML_FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<StrategyAnalyzerLog>
  <StrategyAnalyzerGridEntry>
    <Action>Backtest</Action>
    <Date>2026-07-11T22:31:05</Date>
    <Instrument>ES 12-26</Instrument>
    <From>2026-01-01</From>
    <Guid>11111111-2222-3333-4444-555555555555</Guid>
    <OptimizationParameters></OptimizationParameters>
    <SummaryPerformances>
      <PerformanceUnit>Currency</PerformanceUnit>
      <SummaryPerformancesSerialize>TotalNetProfit;1234.56;800.11;434.45|ProfitFactor;1.85;2.10;1.40|SharpeRatio;1.22;1.31;0.94|MaxDrawdown;-450.25;-300.00;-150.25|TotalNumTrades;42;28;14|PercentProfitable;61.9;64.3;57.1|NumWinningTrades;26;18;8|NumLosingTrades;16;10;6</SummaryPerformancesSerialize>
    </SummaryPerformances>
    <SummaryPerformances>
      <PerformanceUnit>Percent</PerformanceUnit>
      <SummaryPerformancesSerialize>TotalNetProfit;12.35;8.01;4.34|ProfitFactor;1.85;2.10;1.40</SummaryPerformancesSerialize>
    </SummaryPerformances>
  </StrategyAnalyzerGridEntry>
</StrategyAnalyzerLog>
"""

ANALYZER_CS_FIXTURE = "// source snapshot fixture, not real NinjaScript, for diagnostics only\n"

TRACE_FIXTURE_LINES = [
    "2026-07-11 22:29:58:000 NinjaScriptEditorHotKeys: File='Save' Compile='F5'",
    "2026-07-11 22:29:59:500 Compiling and reloading NinjaTrader.Custom...",
    "2026-07-11 22:30:00:000 Unable to compile custom assembly. Original version has been restored.",
    "2026-07-11 22:30:00:050 1>TestStrategy.cs(42,17): error CS1002: ; expected",
]


def _is_unknown_action(stderr: str) -> bool:
    return "unknown action" in str(stderr or "").lower()


def _check_action(backend, action: str, args: dict, expect_substrings: list[str], label: str) -> Result:
    try:
        result = backend.execute(action, dict(args))
    except Exception as exc:
        return Result("FAIL", label, f"action '{action}' raised an exception: {exc}")

    if _is_unknown_action(result.stderr):
        return Result("WARN", label, f"action '{action}' not yet implemented in file_write backend")

    if not result.success:
        return Result("FAIL", label, f"action '{action}' is implemented but failed: {result.stderr}")

    haystack = dump_text(result.metadata) + " " + str(result.stdout or "")
    missing = [s for s in expect_substrings if s not in haystack]
    if missing:
        return Result(
            "FAIL",
            label,
            f"action '{action}' succeeded but the response is missing expected fixture markers {missing}",
        )
    return Result("PASS", label, f"action '{action}' succeeded and echoed fixture markers {expect_substrings}")


def main() -> int:
    from runtime.backends.file_write import FileWriteBackend

    results: list[Result] = []
    temp_nt8_dir = make_temp_nt8_dir()

    try:
        backend = FileWriteBackend(nt8_data_dir=temp_nt8_dir)

        # strategyanalyzerlogs fixture.
        # since must be an ISO 8601 string, the real _parse_since() in
        # file_write.py calls datetime.fromisoformat() on it directly.
        analyzer_dir = temp_nt8_dir / "strategyanalyzerlogs"
        since_iso = (datetime.now(tz=timezone.utc) - timedelta(seconds=5)).isoformat()
        xml_path = analyzer_dir / "TestStrategy_20260711_01.xml"
        cs_path = analyzer_dir / "TestStrategy_20260711_01.cs"
        xml_path.write_text(ANALYZER_XML_FIXTURE, encoding="utf-8")
        cs_path.write_text(ANALYZER_CS_FIXTURE, encoding="utf-8")

        results.append(
            _check_action(
                backend,
                "analyzer_status",
                {"since": since_iso, "strategy": "TestStrategy"},
                ["TestStrategy"],
                "analyzer_status",
            )
        )
        results.append(
            _check_action(
                backend,
                "analyzer_results",
                {"name": xml_path.name, "strategy": "TestStrategy", "since": since_iso},
                ["1234.56", "TotalNetProfit"],
                "analyzer_results",
            )
        )
        results.append(
            _check_action(
                backend,
                "analyzer_list_results",
                {"strategy": "TestStrategy"},
                ["TestStrategy_20260711_01"],
                "analyzer_list_results",
            )
        )

        # trace fixture.
        trace_dir = temp_nt8_dir / "trace"
        trace_path = trace_dir / "trace.20260711.00001.txt"
        trace_path.write_text("\n".join(TRACE_FIXTURE_LINES) + "\n", encoding="utf-8")

        dll_path = temp_nt8_dir / "bin" / "Custom" / "NinjaTrader.Custom.dll"
        dll_path.write_bytes(b"fixture dll bytes, not a real assembly")
        dll_mtime_before = dll_path.stat().st_mtime

        results.append(
            _check_action(
                backend,
                "compile_status",
                {"dll_mtime_before": dll_mtime_before},
                ["Unable to compile custom assembly"],
                "compile_status",
            )
        )
        results.append(
            _check_action(
                backend,
                "parse_compile_errors",
                # since is intentionally omitted: it is optional, and passing
                # it as a fixed fictional 2026-07-11 timestamp would race the
                # real host clock. file_write.FileWriteBackend._parse_since
                # treats a missing since as no lower bound, and scans every
                # line in the newest trace and log file instead.
                {},
                ["TestStrategy.cs", "CS1002"],
                "parse_compile_errors",
            )
        )

    finally:
        cleanup_temp_dir(temp_nt8_dir)

    return report(results, "test_parsers")


if __name__ == "__main__":
    sys.exit(main())
