#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R8 — Quint semantics split: run vs verify (E1, contract G3).

Drives the rare-path fixture (tests/fixtures/r8/rare.qnt) through both
tools and asserts the evidence-class gap is real: `quint run` with 100
seeded samples misses the defect and exits 0, `quint verify` finds the
counterexample exhaustively at depth 20. Then asserts the pipeline
documents report the two evidence classes correctly: the generator gates
safety on `quint verify` and fails closed when verify is unavailable, the
lifecycle skill no longer presents a clean `quint run` as a bounded check
and its Quint example uses valid syntax (no Some/None), and the
adversarial skill's Step 5 escalates absence claims to verify.

Requires quint + a JVM (Apalache). Exit 0 on pass, 1 on failure,
2 if quint verify cannot run on this machine.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "r8" / "rare.qnt"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def main() -> int:
    if shutil.which("quint") is None:
        print("SKIP-FAIL: quint CLI not on PATH; R8 cannot run", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="r8-") as td:
        spec = Path(td) / "rare.qnt"
        spec.write_text(FIXTURE.read_text())

        run = subprocess.run(
            ["quint", "run", "--invariant=safety", "--max-steps=25",
             "--max-samples=100", "--seed=0x1", str(spec)],
            capture_output=True, text=True, cwd=td, timeout=300,
        )
        check("quint run (100 seeded samples) misses the rare-path defect",
              run.returncode == 0 and "No violation found" in run.stdout,
              f"exit={run.returncode}")

        verify = subprocess.run(
            ["quint", "verify", "--invariant=safety", "--max-steps=20", str(spec)],
            capture_output=True, text=True, cwd=td, timeout=600,
        )
        out = verify.stdout + verify.stderr
        if "apalache" in out.lower() and ("java" in out.lower() and verify.returncode != 1):
            print("SKIP-FAIL: quint verify unavailable (Apalache/JVM)", file=sys.stderr)
            return 2
        check("quint verify finds the defect exhaustively at depth 20",
              verify.returncode != 0 and "counterexample" in out,
              f"exit={verify.returncode}")

    body = (REPO / "agents" / "fv-quint-spec-generator.md").read_text()
    check("generator: safety gate is quint verify, labeled bounded-checked",
          "quint verify --invariant=$SAFETY_INVARIANT" in body
          and "bounded-checked to depth 30" in body)
    check("generator: quint run pass labeled simulation evidence only",
          "simulation evidence only" in body)
    check("generator: verify-unavailable fails closed, no run substitution",
          "quint-verify-unavailable" in body
          and "not a substitute" in body)
    check("generator: checks recorded per G3 (version, seeds, backend, depth)",
          "## Checks run" in body and "seeds/samples" in body)


    life = (REPO / "skills" / "fv-lifecycle-adversary" / "SKILL.md").read_text()
    check("lifecycle: Quint example has no Some/None",
          "Some(" not in life and "= None" not in life)
    check("lifecycle: absence claims escalate to quint verify",
          "quint verify --invariant" in life)
    check("lifecycle: clean run never presented as bounded check",
          "Never label a clean `quint run` as a bounded check" in life
          and "held under 10-step bound" not in life)
    check("lifecycle: bounded-checked records depth/backend/version",
          "bounded-checked (verify, depth=10, apalache" in life)

    adv = (REPO / "skills" / "fv-adversarial" / "SKILL.md").read_text()
    check("adversarial Step 5: verify escalation before absence claims",
          "Certify absence" in adv and "quint verify --invariant <inv_name>" in adv)
    check("adversarial Step 5: temporal properties via --temporal",
          "--temporal" in adv)
    check("adversarial Step 5: simulation-only labeled visibly weaker",
          "simulation-only (samples=M, seed=S)" in adv)
    check("adversarial Step 5: no 'held under bound' claims from run",
          "held under bound" not in adv)

    print()
    if FAILURES:
        print(f"R8: {len(FAILURES)} failure(s)")
        return 1
    print("R8: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
