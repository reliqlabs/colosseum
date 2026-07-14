#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
ci — single local CI entry point for the Colosseum repo (C10).

Runs the repository gates in order and aggregates one verdict. Each check
is pass / fail / incomplete. A failing check fails the run (nonzero exit).
An INCOMPLETE regression suite (a test suite that could not run because a
verification toolchain is absent) is a non-fatal warning by default;
--strict makes it fatal too.

CHECKS (in order)
  frontmatter       scripts/validate_frontmatter.py
  agent-lint        scripts/install-agents.py lint
  roster-drift      scripts/gen_roster_docs.py --check
  doc-links         scripts/check_doc_links.py
  dispatch-config   scripts/check_dispatch_config.py --selftest
  fixture-tracking  no untracked files under tests/fixtures (a fixture the
                    working tree has but git does not ships broken clones)
  regression        tests/run_all.py  (Part IV suite: parser/version
                    fixtures, MCP smoke, race, injection, all r*.py)

USAGE
    ci.py [--strict] [--only frontmatter,doc-links,...]

EXIT  0 passed | 1 a check failed (or INCOMPLETE under --strict) | 2 usage
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# name -> (argv, is_regression). Regression maps run_all's exit 3 to
# INCOMPLETE; every other check treats nonzero as FAIL.
CHECKS: list[tuple[str, list[str], bool]] = [
    ("frontmatter", ["uv", "run", "--script", str(REPO / "scripts/validate_frontmatter.py")], False),
    ("agent-lint", [str(REPO / "scripts/install-agents.py"), "lint"], False),
    ("roster-drift", ["uv", "run", "--script", str(REPO / "scripts/gen_roster_docs.py"), "--check"], False),
    ("doc-links", ["uv", "run", "--script", str(REPO / "scripts/check_doc_links.py")], False),
    ("dispatch-config", ["uv", "run", "--script", str(REPO / "scripts/check_dispatch_config.py"), "--selftest"], False),
    # Untracked fixture files pass local CI (which sees the working tree)
    # but break every fresh clone; the global .colosseum/ gitignore hid the
    # r22/r28 fixture manifests exactly this way. Empty output = pass.
    ("fixture-tracking", ["bash", "-c",
                          f"cd {REPO} && u=$(git ls-files --others --exclude-standard tests/fixtures) && "
                          "if [ -n \"$u\" ]; then echo \"untracked fixture files (fresh clones will miss them):\"; "
                          "echo \"$u\"; exit 1; fi"], False),
    ("regression", ["uv", "run", "--script", str(REPO / "tests/run_all.py")], True),
]


def run_check(name: str, argv: list[str], is_regression: bool) -> tuple[str, float, str]:
    t0 = time.monotonic()
    proc = subprocess.run(argv, capture_output=True, text=True)
    elapsed = time.monotonic() - t0
    rc = proc.returncode
    if rc == 0:
        status = "PASS"
    elif is_regression and rc == 3:
        status = "INCOMPLETE"
    else:
        status = "FAIL"
    tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-20:])
    return status, elapsed, tail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="treat an INCOMPLETE regression suite as a failure")
    ap.add_argument("--only", default=None, help="comma-separated check names")
    args = ap.parse_args()

    checks = CHECKS
    if args.only:
        wanted = {w.strip() for w in args.only.split(",") if w.strip()}
        unknown = wanted - {c[0] for c in CHECKS}
        if unknown:
            print(f"error: unknown check(s): {sorted(unknown)}; "
                  f"have {[c[0] for c in CHECKS]}", file=sys.stderr)
            return 2
        checks = [c for c in CHECKS if c[0] in wanted]

    print("=" * 60)
    print("Colosseum repository CI")
    print("=" * 60)

    results: list[tuple[str, str, float]] = []
    for name, argv, is_regression in checks:
        status, elapsed, tail = run_check(name, argv, is_regression)
        mark = {"PASS": "✓", "INCOMPLETE": "~", "FAIL": "✗"}[status]
        print(f"  {mark} {name:16} {status:11} ({elapsed:.0f}s)")
        if status != "PASS":
            print("      " + tail.replace("\n", "\n      "))
        results.append((name, status, elapsed))

    failed = [n for n, s, _ in results if s == "FAIL"]
    incomplete = [n for n, s, _ in results if s == "INCOMPLETE"]
    total = sum(e for _, _, e in results)

    print("=" * 60)
    if failed:
        print(f"CI FAILED — {len(failed)} check(s) failed: {', '.join(failed)} ({total:.0f}s)")
        return 1
    if incomplete and args.strict:
        print(f"CI FAILED (--strict) — {len(incomplete)} incomplete: "
              f"{', '.join(incomplete)} ({total:.0f}s)")
        return 1
    if incomplete:
        print(f"CI PASSED with {len(incomplete)} INCOMPLETE (toolchain absent): "
              f"{', '.join(incomplete)} ({total:.0f}s)")
        return 0
    print(f"CI PASSED — all {len(results)} checks green ({total:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
