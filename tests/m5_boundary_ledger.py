#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
M5 — boundary skill + ledger versioning regression.

Asserts:
  1. the colosseum-boundary skill frontmatter passes validate_frontmatter;
  2. check_ledger_version classifies v1 / bare / unknown / malformed with
     the mandated exit codes;
  3. a versioned envelope gates identically to the equivalent bare list
     through check_evidence_records (the load_records unwrap is verdict-
     neutral);
  4. the system-intent template carries the A*/G*/composition structure.

Infra check (not a Part IV fixture).
exit 0 all assertions hold; 1 a failure; 2 a required file/tool absent.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FM = ROOT / "scripts" / "validate_frontmatter.py"
LV = ROOT / "scripts" / "check_ledger_version.py"
GATE = ROOT / "scripts" / "check_evidence_records.py"
SKILL = ROOT / "skills" / "colosseum-boundary" / "SKILL.md"
TEMPLATE = ROOT / "templates" / "system-intent.template.md"
FIX = ROOT / "tests" / "fixtures" / "m5"

failures: list[str] = []


def run(script: Path, args: list[str]) -> tuple[int, str, str]:
    p = subprocess.run([sys.executable, str(script), *args],
                       capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def run_exec(script: Path, args: list[str]) -> tuple[int, str, str]:
    """Invoke via the script's own `uv run --script` shebang so its
    declared dependencies (e.g. pyyaml for the frontmatter validator) are
    present. Plain sys.executable lacks them."""
    p = subprocess.run([str(script), *args], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}: {detail}")
        failures.append(name)


def verdict_of(stderr: str) -> str:
    for ln in stderr.splitlines():
        if ln.startswith("VERDICT:"):
            return ln.split(":", 1)[1].strip()
    return "<none>"


def main() -> int:
    for needed in (FM, LV, GATE, SKILL, TEMPLATE, FIX):
        if not needed.exists():
            print(f"SKIP-FAIL: missing {needed}", file=sys.stderr)
            return 2

    # 1. boundary skill frontmatter is valid (validator sweeps all skills).
    #    Run through the uv shebang so pyyaml is available.
    code, out, err = run_exec(FM, [])
    check("validate_frontmatter green (incl. colosseum-boundary)",
          code == 0, f"exit={code}: {err.strip()[:200]}")
    check("boundary skill was seen by the validator",
          "colosseum-boundary" not in err, err.strip()[:200])

    # 2. check_ledger_version exit-code contract.
    code, _, err = run(LV, ["--ledger", str(FIX / "records-envelope.json")])
    check("v1 envelope -> exit 0", code == 0, f"exit={code}")
    check("v1 envelope reports OK", verdict_of(err) == "OK", verdict_of(err))

    code, _, err = run(LV, ["--ledger", str(FIX / "records-bare.json")])
    check("bare list -> exit 0 (unversioned)", code == 0, f"exit={code}")
    check("bare list warns unversioned",
          "unversioned" in err.lower(), err.strip())

    code, _, err = run(LV, ["--ledger", str(FIX / "unknown-version.json")])
    check("unknown version -> exit 2", code == 2, f"exit={code}")
    check("unknown version REJECTED", verdict_of(err) == "REJECTED", verdict_of(err))

    code, _, err = run(LV, ["--ledger", str(FIX / "no-version-envelope.json")])
    check("records key without version -> exit 2 (malformed)",
          code == 2, f"exit={code}")

    # 3. versioned envelope gates identically to the bare list. Same records,
    #    same required set -> same verdict + exit through check_evidence_records.
    req = ["--require", "B1,S1"]
    c_env, _, e_env = run(GATE, ["--records", str(FIX / "records-envelope.json"), *req])
    c_bare, _, e_bare = run(GATE, ["--records", str(FIX / "records-bare.json"), *req])
    check("envelope verdict == bare verdict",
          verdict_of(e_env) == verdict_of(e_bare),
          f"env={verdict_of(e_env)} bare={verdict_of(e_bare)}")
    check("envelope exit == bare exit", c_env == c_bare, f"{c_env} vs {c_bare}")
    check("both PASS to VERIFIED[..] (records are all-PASS)",
          verdict_of(e_bare).startswith("VERIFIED["), verdict_of(e_bare))

    # 4. system-intent template structure.
    tpl = TEMPLATE.read_text()
    for needle in ("Assume clauses — `A*`", "Guarantee clauses — `G*`",
                   "Composition graph", "ledger_schema_version",
                   "Open composition obligations"):
        check(f"template has section: {needle!r}", needle in tpl, "absent")

    print()
    if failures:
        print(f"M5 FAILED — {len(failures)} assertion(s): {', '.join(failures)}",
              file=sys.stderr)
        return 1
    print("M5 PASSED — boundary skill valid, ledger versioning + envelope "
          "unwrap verdict-neutral", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
