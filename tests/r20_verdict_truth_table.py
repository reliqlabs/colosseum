#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R20 — G2 verdict aggregation truth table (E4).

Drives every row of the aggregation table through pyramid_run.py's pure
aggregate_verdict function: failed dominates, any required gap (skipped /
not_run / not_applicable) yields exactly INCOMPLETE, all-passed yields the
scoped VERIFIED[<profile>], and non-required layers never gate. Then runs
the headless runner end-to-end against the fixture crate: tested profile
passes with exit 0, a required-layer skip yields INCOMPLETE exit 3, the
proved profile is INCOMPLETE headless (lean is agent-flow), and a broken
test yields FAILED exit 1.

Requires cargo. Exit 0 pass, 1 fail, 2 toolchain unavailable.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "scripts" / "pyramid_run.py"
FIXTURE = REPO / "tests" / "fixtures" / "r20" / "minicrate"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def load_runner():
    spec = importlib.util.spec_from_file_location("pyramid_run", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(crate: Path, profile: str, *extra: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["uv", "run", "--script", str(RUNNER), "--crate", str(crate),
         "--profile", profile, *extra],
        capture_output=True, text=True, timeout=900,
    )
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    mod = load_runner()
    agg = mod.aggregate_verdict
    REQ = ["types", "lints", "proptests"]

    rows = [
        # (statuses, expected verdict, expected exit)
        ({"types": "passed", "lints": "passed", "proptests": "passed"},
         "VERIFIED[tested]", 0),
        ({"types": "passed", "lints": "failed", "proptests": "passed"},
         "FAILED", 1),
        ({"types": "failed", "lints": "not_run", "proptests": "not_run"},
         "FAILED", 1),
        ({"types": "passed", "lints": "failed", "proptests": "skipped"},
         "FAILED", 1),  # failed dominates gaps
        ({"types": "passed", "lints": "passed", "proptests": "skipped"},
         "INCOMPLETE", 3),
        ({"types": "passed", "lints": "passed", "proptests": "not_applicable"},
         "INCOMPLETE", 3),
        ({"types": "passed", "lints": "passed"},  # missing entirely
         "INCOMPLETE", 3),
    ]
    for statuses, want_verdict, want_code in rows:
        verdict, code = agg("tested", REQ, statuses)
        check(f"table: {statuses} -> {want_verdict}",
              verdict == want_verdict and code == want_code,
              f"got {verdict}/{code}")

    verdict, code = agg("tested", REQ,
                        {"types": "passed", "lints": "passed",
                         "proptests": "passed", "fuzz": "failed"})
    check("table: non-required layer failure does not gate the profile verdict",
          verdict == "VERIFIED[tested]" and code == 0, f"got {verdict}/{code}")

    verdict, code = agg("bounded", REQ + ["kani"],
                        {"types": "passed", "lints": "passed",
                         "proptests": "passed", "kani": "not_applicable"})
    check("table: zero Kani harnesses under bounded is INCOMPLETE, not passed",
          verdict == "INCOMPLETE" and code == 3, f"got {verdict}/{code}")

    if shutil.which("cargo") is None:
        print("SKIP-FAIL: cargo not on PATH; live-runner half skipped",
              file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="r20-") as td:
        crate = Path(td) / "minicrate"
        shutil.copytree(FIXTURE, crate)

        code, out = run(crate, "tested")
        check("runner: tested profile on clean crate -> VERIFIED[tested], exit 0",
              code == 0 and "VERIFIED[tested]" in out, f"exit={code}")
        reports = list((crate / ".colosseum" / "verify").glob("headless-*.json"))
        check("runner: JSON report persisted with verdict",
              reports and json.loads(reports[-1].read_text())["verdict"] == "VERIFIED[tested]")

        code, out = run(crate, "tested", "--skip", "proptests")
        check("runner: skipped required layer -> INCOMPLETE, exit 3",
              code == 3 and "INCOMPLETE" in out, f"exit={code}")

        code, out = run(crate, "proved")
        check("runner: proved profile headless -> INCOMPLETE (lean is agent-flow)",
              code == 3 and "INCOMPLETE" in out, f"exit={code}")

        lib = crate / "src" / "lib.rs"
        lib.write_text(lib.read_text().replace("add(2, 2), 4", "add(2, 2), 5"))
        code, out = run(crate, "tested")
        check("runner: failing test -> FAILED, exit 1",
              code == 1 and "FAILED" in out, f"exit={code}")

    print()
    if FAILURES:
        print(f"R20: {len(FAILURES)} failure(s)")
        return 1
    print("R20: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
