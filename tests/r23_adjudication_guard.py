#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R23 (static half) — minimal adjudication guard (Z4, contract G4).

Asserts the adversarial skill's synthesis/closure rules encode G4: findings
close only on evidence, support counts triage but never close, contested
findings are retained with hypothesis and evidence rather than resolved by
majority or synthesizer fiat, refutations require cites, no adjudicator
upgrades missing/failed evidence to PASS/VERIFIED, and second-model checks
are blinded. Also asserts the old confirmation-seeking Step 8 language
(inline the finding, treat rediscovery as confirmation) is gone.

The live half of R23 (a contested fixture finding driven through an actual
synthesis) is a behavioral harness run over these rules; the full critique
loop with cross-critique/defense rounds lands with C3/R25.

Exit 0 on pass, 1 on failure.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skills" / "colosseum-adversarial" / "SKILL.md"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def main() -> int:
    text = SKILL.read_text()

    check("skill has the G4 adjudication-and-closure section",
          "### Adjudication and closure" in text and "contract G4" in text)
    check("closure only on evidence, with the evidence classes named",
          "closes only on evidence" in text
          and "reproducible counterexample" in text
          and "failing test" in text
          and "proof obligation" in text
          and "human ruling" in text)
    check("support counts triage, never close",
          "Support counts triage; they never close." in text)
    check("contested findings stay open with hypothesis and evidence retained",
          "Contested findings stay open." in text
          and "CONTESTED" in text
          and "original hypothesis" in text
          and "what evidence would decide it" in text)
    check("no dismissal by synthesizer fiat; refutations require cites",
          "No dismissal by fiat." in text
          and "A refutation without a cite does not close the finding" in text)
    check("no adjudicator upgrades missing/failed evidence to PASS/VERIFIED",
          "converts missing, failed, or incomplete mechanical evidence into PASS or VERIFIED"
          in text)
    check("waivers narrow scope, never upgrade verdicts",
          "waiver narrows the claimed scope visibly" in text)
    check("second-model checks are blinded",
          "Second-model checks are blinded." in text)

    check("old confirmation-seeking language removed",
          "treat as confirmed" not in text
          and "finding inlined as context" not in text)
    check("Step 8 unique-critical path routes through blinded G4 check",
          "blinded second check per G4" in text)

    print()
    if FAILURES:
        print(f"R23 static: {len(FAILURES)} failure(s)")
        return 1
    print("R23 static: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
