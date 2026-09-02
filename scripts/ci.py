#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Single fail-closed CI entry point for FV."""
from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECKS: list[tuple[str, list[str], bool]] = [
    ("frontmatter", ["uv", "run", "--script", str(REPO / "scripts" / "validate_frontmatter.py")], False),
    ("roster-drift", ["python3", str(REPO / "scripts" / "gen_roster_docs.py"), "--check"], False),
    ("doc-links", ["python3", str(REPO / "scripts" / "check_doc_links.py")], False),
    ("dispatch-config", ["python3", str(REPO / "scripts" / "check_dispatch_config.py"), "--selftest"], False),
    ("fixture-tracking", ["python3", str(REPO / "scripts" / "check_fixture_tracking.py")], False),
    ("regression", ["python3", str(REPO / "tests" / "run_all.py")], True),
]


def run_check(command: list[str], regression: bool) -> tuple[str, float, str]:
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, text=True)
    elapsed = time.monotonic() - started
    if result.returncode == 0:
        status = "PASS"
    elif regression and result.returncode == 3:
        status = "INCOMPLETE"
    else:
        status = "FAIL"
    tail = "\n".join((result.stdout + result.stderr).splitlines()[-20:])
    return status, elapsed, tail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tolerate-incomplete",
        action="store_true",
        help="allow regression exit 3 on intentionally toolchain-incomplete runners",
    )
    parser.add_argument("--only", default=None, help="comma-separated check names")
    args = parser.parse_args()
    checks = CHECKS
    if args.only:
        wanted = {item.strip() for item in args.only.split(",") if item.strip()}
        known = {item[0] for item in CHECKS}
        unknown = wanted - known
        if unknown:
            print(f"error: unknown check(s): {sorted(unknown)}; have {sorted(known)}")
            return 2
        checks = [item for item in CHECKS if item[0] in wanted]

    results: list[tuple[str, str, float]] = []
    for name, command, regression in checks:
        status, elapsed, tail = run_check(command, regression)
        print(f"  [{status:>10}] {name:16} ({elapsed:.1f}s)")
        if status != "PASS" and tail:
            print("      " + tail.replace("\n", "\n      "))
        results.append((name, status, elapsed))
    failed = [name for name, status, _ in results if status == "FAIL"]
    incomplete = [name for name, status, _ in results if status == "INCOMPLETE"]
    if failed:
        print(f"CI FAILED: {', '.join(failed)}")
        return 1
    if incomplete and not args.tolerate_incomplete:
        print(f"CI FAILED: incomplete checks: {', '.join(incomplete)}")
        return 1
    if incomplete:
        print(f"CI PASSED with tolerated INCOMPLETE: {', '.join(incomplete)}")
        return 0
    print(f"CI PASSED: {len(results)} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
