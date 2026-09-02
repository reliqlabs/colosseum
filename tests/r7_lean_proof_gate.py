#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R7 — proof-sensitive Lean gate (E2, contract G2).

Demonstrates the false-green (`lake build` exits 0 on a sorry-admitted
theorem) against the fixture project, then asserts the axiom gate maps it
to exactly INCOMPLETE with sorryAx flagged, while an axiom-clean scope is
VERIFIED[axiom-clean]. Also asserts the verify skill's Layer 8 carries no
text-scan fallback and routes through the audit.

Requires lean + lake on PATH. Exit 0 on pass, 1 on failure, 2 if the
toolchain is unavailable.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "r7"
GATE = REPO / "scripts" / "lean_axiom_gate.py"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def gate(project: Path, theorems: str) -> tuple[int, dict]:
    proc = subprocess.run(
        ["uv", "run", "--script", str(GATE), "--project", str(project),
         "--module", "R7", "--theorems", theorems, "--json"],
        capture_output=True, text=True, timeout=600,
    )
    try:
        record = json.loads(proc.stdout)
    except json.JSONDecodeError:
        record = {"_raw": proc.stdout, "_stderr": proc.stderr}
    return proc.returncode, record


def main() -> int:
    if shutil.which("lake") is None or shutil.which("lean") is None:
        print("SKIP-FAIL: lean/lake not on PATH; R7 cannot run", file=sys.stderr)
        return 2
    for command in (["lean", "--version"], ["lake", "--version"]):
        probe = subprocess.run(command, capture_output=True, text=True)
        if probe.returncode != 0:
            print(f"SKIP-FAIL: Lean toolchain is not configured: {(probe.stderr or probe.stdout).strip()}",
                  file=sys.stderr)
            return 2

    with tempfile.TemporaryDirectory(prefix="r7-") as td:
        project = Path(td) / "proj"
        shutil.copytree(FIXTURE, project)

        build = subprocess.run(["lake", "build"], cwd=project,
                               capture_output=True, text=True, timeout=600)
        out = build.stdout + build.stderr
        check("false-green demonstrated: lake build exits 0 despite sorry",
              build.returncode == 0 and "sorry" in out,
              f"exit={build.returncode}")

        code, rec = gate(project, "complete_thm,incomplete_thm")
        check("sorry-admitted scope: verdict is exactly INCOMPLETE",
              rec.get("verdict") == "INCOMPLETE" and code == 1,
              f"exit={code}, verdict={rec.get('verdict')}")
        check("axiom audit flags sorryAx on the admitted theorem",
              rec.get("axioms_by_theorem", {}).get("incomplete_thm") == ["sorryAx"])
        check("proven theorem audits clean in the same record",
              rec.get("axioms_by_theorem", {}).get("complete_thm") == [])

        code, rec = gate(project, "complete_thm")
        check("axiom-clean scope: verdict is VERIFIED[axiom-clean]",
              rec.get("verdict") == "VERIFIED[axiom-clean]" and code == 0,
              f"exit={code}, verdict={rec.get('verdict')}")
        check("clean verdict still records the project's sorry warnings",
              rec.get("build_sorry_warnings", 0) >= 0
              and "build_sorry_warnings" in rec)

        code, rec = gate(project, "complete_thm,no_such_thm")
        check("unknown theorem name: verdict is FAILED, not passed",
              rec.get("verdict") == "FAILED" and code == 2,
              f"exit={code}, verdict={rec.get('verdict')}")

    gate_src = GATE.read_text()
    check("gate has no text-scan mode", "grep" not in gate_src.lower()
          or "proves nothing" in gate_src)

    skill = (REPO / "skills" / "fv-verify" / "SKILL.md").read_text()
    check("Layer 8: text-scan fallback removed from verify skill",
          "scan for `sorry` markers" not in skill
          and "no text-scan fallback" in skill)
    check("Layer 8: sorry-admitted maps to exactly INCOMPLETE, never passed",
          "exactly `INCOMPLETE`" in skill and "never `passed`" in skill)
    check("Layer 8: green build is not proof evidence",
          "proof-insensitive" in skill)
    check("Layer 8: builds run inside the Z2 environment",
          "Z2 environment" in skill and "executes arbitrary metacode" in skill)
    check("Layer 8: missing Lake project fails as not-auditable",
          "not-auditable" in skill)

    print()
    if FAILURES:
        print(f"R7: {len(FAILURES)} failure(s)")
        return 1
    print("R7: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
