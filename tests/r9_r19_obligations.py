#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R9 + R19 — frozen obligation manifests and obligation-quality checks (E3).

R9: a generator run that weakens a required invariant produces a proposal
diff, not a green run. The weakened `x >= 1` -> `x >= 0` still passes
`quint verify` (the truth of the weaker formula is exactly why weakening
is dangerous), so only the frozen definition pin catches it: the checker
must return PROPOSAL with the diff while its safety obligation stays
green.

R19: vacuous invariant (literally true), disabled transition (false
guard), and unreachable witness fixtures are each caught by the checker's
quality checks, with honest evidence classes on the records.

Also asserts the generator body's E3 contract: STATUS is a proposal, the
invariant-latitude language is gone, SPEC_FILENAME is honored (no
hardcoded rcv.qnt outside the example), and the manifest is named
generator-unwritable in the wrapper permissions.

Requires quint + JVM. Exit 0 pass, 1 fail, 2 toolchain unavailable.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "r19"
CHECKER = REPO / "scripts" / "obligation_check.py"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def run_checker(manifest: Path, *extra: str) -> tuple[int, dict]:
    proc = subprocess.run(
        ["uv", "run", "--script", str(CHECKER), "--manifest", str(manifest),
         "--json", *extra],
        capture_output=True, text=True, timeout=900,
    )
    try:
        record = json.loads(proc.stdout)
    except json.JSONDecodeError:
        record = {"_stderr": proc.stderr[-500:]}
    return proc.returncode, record


def unmet(record: dict, obligation: str) -> list[str]:
    return [r["target"] for r in record.get("results", [])
            if r["obligation"] == obligation and not r["ok"]]


def main() -> int:
    if shutil.which("quint") is None:
        print("SKIP-FAIL: quint not on PATH", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="r9r19-") as td:
        work = Path(td) / "proj"
        shutil.copytree(FIXTURE, work)

        # R19 good manifest: all obligations met
        code, rec = run_checker(work / "obligations-good.json")
        check("R19: compliant spec is ACCEPTED (exit 0)",
              code == 0 and rec.get("verdict") == "ACCEPTED",
              f"exit={code}, verdict={rec.get('verdict')}")

        # R19 bad manifest: the three quality defects, each caught
        code, rec = run_checker(work / "obligations-bad.json")
        check("R19: defect manifest is PROPOSAL (nonzero exit)",
              code == 1 and rec.get("verdict") == "PROPOSAL",
              f"exit={code}, verdict={rec.get('verdict')}")
        check("R19: vacuous invariant caught",
              unmet(rec, "vacuity") == ["inv_vacuous"],
              f"got {unmet(rec, 'vacuity')}")
        check("R19: unreachable witness caught",
              unmet(rec, "reachability") == ["witness_unreachable"],
              f"got {unmet(rec, 'reachability')}")
        check("R19: disabled transition caught",
              unmet(rec, "enabledness") == ["never"],
              f"got {unmet(rec, 'enabledness')}")
        reach_ok = [r for r in rec["results"]
                    if r["obligation"] == "reachability" and r["ok"]]
        check("R19: reachable witness evidence class is a run trace",
              any("witnessed" in r["evidence_class"] for r in reach_ok))
        reach_bad = [r for r in rec["results"]
                     if r["obligation"] == "reachability" and not r["ok"]]
        check("R19: unreachability evidence class is bounded-checked with depth",
              any("bounded-checked" in r["evidence_class"] and "depth=" in r["evidence_class"]
                  for r in reach_bad))

        # R9: pin, weaken, expect proposal diff while safety stays green
        code, _ = run_checker(work / "obligations-good.json", "--pin")
        pinned = json.loads((work / "obligations-good.json").read_text())
        check("R9: --pin froze the definition hash into the manifest",
              code == 0 and all(inv.get("definition_sha256")
                                for inv in pinned["invariants"]))

        spec = work / "specs" / "flow.qnt"
        spec.write_text(spec.read_text().replace(
            "val inv_positive = x >= 1", "val inv_positive = x >= 0"))
        code, rec = run_checker(work / "obligations-good.json")
        check("R9: weakened required invariant yields PROPOSAL, not green",
              code == 1 and rec.get("verdict") == "PROPOSAL",
              f"exit={code}, verdict={rec.get('verdict')}")
        check("R9: frozen-pin obligation is the one that failed",
              unmet(rec, "frozen") == ["inv_positive"])
        check("R9: proposal diff carries the weakened definition",
              any(d["invariant"] == "inv_positive"
                  and "x >= 0" in d["proposed_definition"]
                  for d in rec.get("proposal_diffs", [])))
        safety = [r for r in rec["results"] if r["obligation"] == "safety"]
        check("R9: safety verify alone would have passed the weakened spec",
              safety and all(r["ok"] for r in safety))

    body = (REPO / "agents" / "quint-spec-generator-body.md").read_text()
    check("generator: STATUS is a proposal, checker accepts",
          "STATUS: proposal" in body and "STATUS: ok" not in body
          and "obligation_check.py" in body)
    check("generator: invariant-weakening latitude removed",
          "decide whether the spec or the invariant is wrong" not in body
          and "not yours to weaken" in body
          and "invariant-dispute" in body)
    check("generator: SPEC_FILENAME honored, no hardcoded spec name",
          "OUTPUT_DIR/$SPEC_FILENAME" in body
          and "OUTPUT_DIR/rcv.qnt" not in body)
    check("generator: project-specific section refs parameterized",
          "§2.5 blocks" not in body and "B9's negligibility" not in body)

    wrapper = (REPO / "agents" / "opencode" / "quint-spec-generator.md").read_text()
    check("wrapper: obligation manifest generator-unwritable",
          '"**/.colosseum/obligations*": deny' in wrapper)

    print()
    if FAILURES:
        print(f"R9/R19: {len(FAILURES)} failure(s)")
        return 1
    print("R9/R19: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
