#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R25 (static half) — critique loop under G4, blinded framing, delta mode (C3).

Asserts the adversarial skill defines the three-round critique loop
(cross-critique / defense / re-cross-critique) with G4 semantics
(concession prioritizes, evidence closes), blinded re-review framing that
forbids inlining conclusions, the delta attack mode fv-change
invokes, the mandatory holistic pass alongside slice dispatch, and the
dual spec+intent citation fields in the agent report schema. Also drives
`fv_run.py init --phase` and asserts run.json records the phase.

The live half (an actual critique/defense round over a real contested
finding) is an OMP-native harness run over these mechanisms.

Exit 0 pass, 1 fail.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def main() -> int:
    adv = (REPO / "skills" / "fv-adversarial" / "SKILL.md").read_text()
    body = (REPO / "agents" / "fv-spec-adversary.md").read_text()
    change = (REPO / "skills" / "fv-change" / "SKILL.md").read_text()

    # Critique loop, G4 semantics.
    check("critique loop section exists with all three rounds",
          "Step 7.5: The critique loop" in adv
          and "cross-critique" in adv and "defense" in adv
          and "re-cross-critique" in adv)
    check("G4: concession prioritizes, only evidence closes",
          "near-unanimous concession prioritizes; only evidence closes" in adv.lower()
          or ("concession prioritizes" in adv and "only evidence closes" in adv))
    check("defense concession mandates priority, does not close",
          "It does not close the finding" in adv)
    check("cross-critique blinding named (no other critiques/verdicts shown)",
          "never another reviewer's critique" in adv
          and "never any prior verdict" in adv)
    check("re-cross-critique mandatory for load-bearing revisions",
          "MANDATORY whenever the revision touches a load-bearing" in adv)
    check("Q1/Q2/Q3 protocol described",
          "Q1" in adv and "Q2" in adv and "Q3" in adv)
    check("max reasoning variant required for critique rounds",
          "maximum reasoning variant" in adv)

    # Blinded re-review framing (R25 core).
    check("blinded re-review framing template present",
          "REVIEW_QUESTION" in adv)
    check("framing forbids inlining conclusion/verdict/severity",
          "NEVER inlines the original finding's conclusion" in adv)
    check("rediscovery corroborates, does not close",
          "it does not close" in adv)

    # Delta attack mode, defined and invocable.
    check("delta mode defined with invocation fields",
          "ATTACK_MODE: delta" in adv and "PRIOR_SPEC" in adv
          and "CURRENT_SPEC" in adv and "DELTA_SUMMARY" in adv)
    check("delta insufficiency conditions trigger full re-attack",
          "Delta mode is insufficient" in adv and "full re-attack" in adv)
    check("fv-change invokes delta mode by name",
          "delta attack mode" in change and "ATTACK_MODE: delta" in change)
    check("agent body defines delta as invocation mode C",
          "**C. Delta**" in body and "blast radius" in body)

    # Holistic pass + dual citations.
    check("holistic pass mandatory alongside slices",
          "Mandatory holistic pass" in adv
          and "only of per-section slices is invalid" in adv.replace("consisting ", ""))
    check("slice schema carries dual spec+intent citations",
          "Cite (spec, in-slice)" in body and "Cite (intent)" in body)
    check("intent citations exempt from in-slice rule",
          "INTENT citations may point anywhere" in body)

    wrapper = REPO / "agents" / "fv-spec-adversary.md"
    check("static agent carries dual citations", "Cite (intent)" in wrapper.read_text())

    # Phase field in the run manifest.
    with tempfile.TemporaryDirectory(prefix="r25-") as td:
        target = Path(td) / "intent.md"
        target.write_text("# intent\n")
        run_dir = Path(td) / "run"
        r = subprocess.run(
            ["uv", "run", "--script", str(REPO / "scripts" / "fv_run.py"),
             "init", str(target), "--voices=v1", "--owners=v1:omp",
             f"--run-dir={run_dir}", "--phase", "critique"],
            capture_output=True, text=True, timeout=120)
        manifest = json.loads((run_dir / "run.json").read_text()) \
            if (run_dir / "run.json").exists() else {}
        check("fv_run init --phase recorded in run.json",
              r.returncode == 0 and manifest.get("phase") == "critique",
              f"exit={r.returncode}, phase={manifest.get('phase')}")
        s = subprocess.run(
            ["uv", "run", "--script", str(REPO / "scripts" / "fv_run.py"),
             "status", str(run_dir)], capture_output=True, text=True, timeout=120)
        check("status shows the phase", "phase:  critique" in s.stdout)

    print()
    if FAILURES:
        print(f"R25 static: {len(FAILURES)} failure(s)")
        return 1
    print("R25 static: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
