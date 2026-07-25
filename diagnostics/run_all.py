"""Runs the full nt8-api-control diagnostics suite with the project venv python.

Exit code 0 only if no suite reported a FAIL. WARN lines are printed but do not
affect the exit code, they mark work that other workstreams have not landed yet.

Run directly:
    .venv\\Scripts\\python.exe diagnostics\\run_all.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DIAG_DIR = Path(__file__).resolve().parent
SUITES = ["test_consistency.py", "test_server_boot.py", "test_parsers.py"]


def main() -> int:
    overall_pass = 0
    overall_warn = 0
    overall_fail = 0
    suite_exit_codes: dict[str, int] = {}

    for suite in SUITES:
        suite_path = DIAG_DIR / suite
        print("=" * 70)
        print(f"Running {suite} ...")
        print("=" * 70)
        proc = subprocess.run([sys.executable, str(suite_path)], capture_output=True, text=True)
        print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)

        for line in proc.stdout.splitlines():
            if line.startswith("[PASS]"):
                overall_pass += 1
            elif line.startswith("[WARN]"):
                overall_warn += 1
            elif line.startswith("[FAIL]"):
                overall_fail += 1

        suite_exit_codes[suite] = proc.returncode
        print()

    print("=" * 70)
    print("run_all summary")
    print("=" * 70)
    for suite, code in suite_exit_codes.items():
        status = "OK" if code == 0 else "FAIL"
        print(f"  {suite}: exit {code} ({status})")
    print(f"Totals: {overall_pass} passed, {overall_warn} warned, {overall_fail} failed")

    any_suite_failed = any(code != 0 for code in suite_exit_codes.values())
    if any_suite_failed or overall_fail > 0:
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
