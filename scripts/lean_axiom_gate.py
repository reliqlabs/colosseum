#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
lean_axiom_gate — proof-sensitive Lean gate (E2, contracts G2/G3).

Lean's build is proof-insensitive: a `sorry`-admitted theorem elaborates
with exit 0 and only a warning, so a green `lake build` is NOT evidence
that anything is proven. The only build-level signal of incompleteness is
the axiom record: admitted proofs depend on `sorryAx`. This gate builds
the Lake project, then audits every named theorem with `#print axioms`
and maps the result to a G2 verdict. There is no text-scan mode: grepping
source for `sorry` proves nothing (macros can hide admits, and absence of
the string is not completeness), so this tool never offers it.

SECURITY: `lake build` and `lean` elaboration execute arbitrary metacode
from the project being audited. Run this gate inside the Z2 ephemeral
environment when the Lean source is untrusted (extracted or generated
output), never against a live tree with secrets in reach.

USAGE
    lean_axiom_gate.py --project <lake-project-dir> --module <ImportName> \\
        --theorems thmA,thmB,... [--allow-axiom <name>]... [--json]

VERDICTS (exit code)
    VERIFIED[axiom-clean]  (0)  build ok; every theorem's axioms within the
                                allowed set (default base: Classical.choice,
                                propext, Quot.sound)
    INCOMPLETE             (1)  any theorem depends on sorryAx, or on an
                                axiom outside the allowed set (widen only
                                with an explicit --allow-axiom, which is a
                                visible scope narrowing per G2)
    FAILED                 (2)  build failure, audit error, or unknown
                                theorem name

The audit record (versions, commands, per-theorem axiom sets) is printed
in full; with --json it is machine-readable for the pyramid report.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BASE_AXIOMS = {"Classical.choice", "propext", "Quot.sound"}

_CLEAN_RE = re.compile(r"'([^']+)' does not depend on any axioms")
_DEPENDS_RE = re.compile(r"'([^']+)' depends on axioms: \[([^\]]*)\]")


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, type=Path, help="Lake project root")
    ap.add_argument("--module", required=True, help="module to import for the audit (e.g. the lib name)")
    ap.add_argument("--theorems", required=True, help="comma-separated fully-qualified theorem names")
    ap.add_argument("--allow-axiom", action="append", default=[],
                    help="admit an extra axiom into the allowed set (visible scope narrowing)")
    ap.add_argument("--json", action="store_true", help="emit the audit record as JSON")
    args = ap.parse_args()

    project = args.project.resolve()
    theorems = [t.strip() for t in args.theorems.split(",") if t.strip()]
    allowed = BASE_AXIOMS | set(args.allow_axiom)

    record: dict = {
        "gate": "lean-axiom-audit",
        "project": str(project),
        "module": args.module,
        "theorems": theorems,
        "allowed_axioms": sorted(allowed),
        "lean_version": run(["lean", "--version"], project).stdout.strip(),
        "lake_version": run(["lake", "--version"], project).stdout.strip(),
    }

    def emit(verdict: str, code: int, extra: dict) -> int:
        record.update(extra, verdict=verdict)
        if args.json:
            print(json.dumps(record, indent=2))
        else:
            for k, v in record.items():
                print(f"{k}: {v}")
        print(f"\nVERDICT: {verdict}", file=sys.stderr)
        return code

    build = run(["lake", "build"], project)
    record["build_returncode"] = build.returncode
    record["build_sorry_warnings"] = build.stdout.count("declaration uses `sorry`") \
        + build.stderr.count("declaration uses `sorry`")
    if build.returncode != 0:
        return emit("FAILED", 2, {"reason": "lake build failed",
                                  "build_stderr": build.stderr[-2000:]})

    audit_src = f"import {args.module}\n" + "".join(
        f"#print axioms {t}\n" for t in theorems)
    with tempfile.NamedTemporaryFile("w", suffix=".lean", dir=project,
                                     prefix=".colosseum-audit-", delete=False) as f:
        audit_path = Path(f.name)
        f.write(audit_src)
    try:
        audit = run(["lake", "env", "lean", str(audit_path)], project)
    finally:
        audit_path.unlink(missing_ok=True)

    if audit.returncode != 0:
        return emit("FAILED", 2, {"reason": "axiom audit did not elaborate",
                                  "audit_stderr": (audit.stdout + audit.stderr)[-2000:]})

    axioms_by_thm: dict[str, list[str]] = {}
    for line in audit.stdout.splitlines():
        if m := _CLEAN_RE.search(line):
            axioms_by_thm[m.group(1)] = []
        elif m := _DEPENDS_RE.search(line):
            axioms_by_thm[m.group(1)] = [a.strip() for a in m.group(2).split(",") if a.strip()]
    record["axioms_by_theorem"] = axioms_by_thm

    missing = [t for t in theorems if t not in axioms_by_thm]
    if missing:
        return emit("FAILED", 2, {"reason": f"no audit output for: {missing}"})

    incomplete = {t: ax for t, ax in axioms_by_thm.items() if "sorryAx" in ax}
    nonstandard = {t: sorted(set(ax) - allowed - {"sorryAx"})
                   for t, ax in axioms_by_thm.items()}
    nonstandard = {t: ax for t, ax in nonstandard.items() if ax}

    if incomplete:
        return emit("INCOMPLETE", 1, {
            "reason": f"{len(incomplete)} of {len(theorems)} theorem(s) sorry-admitted",
            "sorry_admitted": sorted(incomplete),
        })
    if nonstandard:
        return emit("INCOMPLETE", 1, {
            "reason": "theorems rest on axioms outside the allowed set "
                      "(pass --allow-axiom to admit them visibly)",
            "nonstandard_axioms": nonstandard,
        })
    return emit("VERIFIED[axiom-clean]", 0,
                {"reason": f"all {len(theorems)} theorem(s) within allowed axiom set"})


if __name__ == "__main__":
    sys.exit(main())
