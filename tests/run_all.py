#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
run_all — P0 regression suite runner.

Discovers tests/r*.py (Part IV fixtures + infra) and tests/m*.py (P2
measurement suites) and runs each. Per-suite exit codes:
0 pass, 1 fail, 2 environment-incomplete (a required toolchain is absent;
the suite could not exercise its fixtures). Runner verdict follows G2:

    any suite failed          -> FAILED      (exit 1)
    else any suite skipped    -> INCOMPLETE  (exit 3)
    else                      -> PASSED      (exit 0)

An environment that cannot run a fixture has not passed it.

USAGE
    tests/run_all.py [--only r7,r14]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None,
                    help="comma-separated fixture prefixes (e.g. r7,r14)")
    args = ap.parse_args()

    suites = sorted(p for p in [*TESTS_DIR.glob("r*.py"), *TESTS_DIR.glob("m*.py")]
                    if p.name != "run_all.py")
    if args.only:
        wanted = {w.strip() for w in args.only.split(",") if w.strip()}
        matched = [p for p in suites
                   if any(p.name.startswith(f"{w}_") or w in p.stem.split("_")
                          for w in wanted)]
        unknown = wanted - {w for w in wanted for p in matched
                            if p.name.startswith(f"{w}_") or w in p.stem.split("_")}
        if unknown:
            sys.exit(f"error: --only matched nothing for: {sorted(unknown)}")
        suites = matched
    if not suites:
        sys.exit("error: no suites found — a zero-suite run is not a pass")

    results: list[tuple[str, int, float]] = []
    for suite in suites:
        t0 = time.monotonic()
        proc = subprocess.run(["uv", "run", "--script", str(suite)],
                              capture_output=True, text=True)
        elapsed = time.monotonic() - t0
        results.append((suite.name, proc.returncode, elapsed))
        label = {0: "pass", 1: "FAIL", 2: "SKIP-FAIL"}.get(proc.returncode,
                                                           f"exit {proc.returncode}")
        print(f"  [{label:>9}] {suite.name} ({elapsed:.0f}s)")
        if proc.returncode == 1:
            tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-15:])
            print("            " + tail.replace("\n", "\n            "))

    failed = [n for n, c, _ in results if c not in (0, 2)]
    skipped = [n for n, c, _ in results if c == 2]
    total_s = sum(e for _, _, e in results)
    print(f"\n{len(results)} suite(s), {total_s:.0f}s total")
    if failed:
        print(f"VERDICT: FAILED ({len(failed)}: {', '.join(failed)})")
        return 1
    if skipped:
        print(f"VERDICT: INCOMPLETE ({len(skipped)} suite(s) could not run: "
              f"{', '.join(skipped)})")
        return 3
    print("VERDICT: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
