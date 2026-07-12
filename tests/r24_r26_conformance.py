#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R24 + R26 — conformance bridge and label surfaces (C2, contract G3).

R24: seeded ITF traces replayed through the fixture Rust adapter. The
faithful adapter passes with the label carrying trace scope; the seeded
divergence (COLOSSEUM_R24_BUG=1 saturates dbl at 64, a bound the spec
does not have) is caught at the exact step, nonzero exit; the --record
output validates through Gate B (check_evidence_records.py) as a
conformance-tested record whose scope survives aggregation.

R26: label surface sweep. REFINEMENT_VERIFIED is emitted by no script and
appears in docs only in negation context; every VERIFIED a script can
emit is scoped (followed by '['); the conformance label's scope string
appears in Gate B's per-claim output.

Requires quint + cargo. Exit 0 pass, 1 fail, 2 toolchain unavailable.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPLAY = REPO / "scripts" / "itf_replay.py"
GATE_B = REPO / "scripts" / "check_evidence_records.py"
FIXTURE = REPO / "tests" / "fixtures" / "r24"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600, **kw)


def main() -> int:
    for tool in ("quint", "cargo"):
        if shutil.which(tool) is None:
            print(f"SKIP-FAIL: {tool} not on PATH; R24 cannot run", file=sys.stderr)
            return 2

    with tempfile.TemporaryDirectory(prefix="r24-") as td:
        work = Path(td) / "proj"
        shutil.copytree(FIXTURE, work, ignore=shutil.ignore_patterns("target"))

        build = run(["cargo", "build", "--quiet"], cwd=work / "adapter")
        check("R24: fixture adapter builds (std-only)", build.returncode == 0,
              build.stderr[-300:])
        adapter = work / "adapter" / "target" / "debug" / "r24-adapter"

        cfg = {
            "spec": "specs/flow.qnt",
            "adapter": [str(adapter.relative_to(work))],
            "n_traces": 5, "max_steps": 15, "max_samples": 200, "seed": "0x1",
            "claim_id": "CONF1",
            "intent": "intent.md",
        }
        cfg_path = work / "replay.json"
        cfg_path.write_text(json.dumps(cfg))

        rec_path = work / "conf1.json"
        r = run(["uv", "run", "--script", str(REPLAY), "--config", str(cfg_path),
                 "--record", str(rec_path)])
        out = r.stdout + r.stderr
        check("R24: faithful adapter conforms (exit 0)", r.returncode == 0,
              f"exit={r.returncode}: {out[-300:]}")
        check("R24: pass label is conformance-tested with trace scope",
              "conformance-tested[traces=5, depth=15, seed=0x1] PASS" in out)

        bug_cfg = {**cfg, "adapter_env": {"COLOSSEUM_R24_BUG": "1"}}
        bug_path = work / "replay-bug.json"
        bug_path.write_text(json.dumps(bug_cfg))
        r = run(["uv", "run", "--script", str(REPLAY), "--config", str(bug_path)])
        out = r.stdout + r.stderr
        check("R24: seeded divergence caught with nonzero exit", r.returncode == 1,
              f"exit={r.returncode}")
        check("R24: first divergent trace and step named",
              "divergence at trace_1.itf.json step 10" in out
              and "spec expects 66, adapter replayed 64" in out)
        check("R24: divergence verdict is FAILED, not a conformance label",
              "VERDICT: FAILED" in out and "conformance-tested[" not in
              out.split("VERDICT:")[-1])

        record = json.loads(rec_path.read_text())
        check("R24: record evidence_class is conformance-tested",
              record["evidence_class"] == "conformance-tested"
              and record["result"] == "PASS")
        check("R24: record binds config as the obligation manifest",
              record["bindings"]["obligation_manifest_hash"] != ""
              and record["bindings"]["parser_schema_version"] == "itf-replay-v1")

        g = run(["uv", "run", "--script", str(GATE_B), "--records", str(rec_path),
                 "--require", "CONF1", "--json"])
        check("R24: record validates through Gate B (exit 0)", g.returncode == 0,
              g.stderr[-200:])
        gj = json.loads(g.stdout)
        check("R26: conformance scope survives Gate B aggregation",
              gj["verdict"].startswith("VERIFIED[")
              and "traces=5, depth=15, seed=0x1" in gj["per_claim"][0].get("scope", ""))

    # ── R26: label surface sweep ───────────────────────────────────────
    scripts = sorted((REPO / "scripts").glob("*.py"))
    offenders = [p.name for p in scripts if "REFINEMENT_VERIFIED" in p.read_text()]
    check("R26: REFINEMENT_VERIFIED emitted by no script", not offenders,
          str(offenders))

    doc_offenders = []
    for p in [REPO / "README.md", REPO / "CONCEPTS.md",
              *sorted((REPO / "skills").glob("*/SKILL.md"))]:
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if "REFINEMENT_VERIFIED" in line and not re.search(
                    r"never|not\b|until|no surface|emitted by no|distinct label",
                    line, re.IGNORECASE):
                doc_offenders.append(f"{p.name}:{i}")
    check("R26: docs mention REFINEMENT_VERIFIED only in negation context",
          not doc_offenders, str(doc_offenders))

    unqualified = []
    for p in scripts:
        for i, line in enumerate(p.read_text().splitlines(), 1):
            for m in re.finditer(r"VERIFIED(?!\[)(?!_)", line):
                if re.search(r"never|bare|unqualified|REFINEMENT", line):
                    continue
                if line.lstrip().startswith("#"):
                    continue
                unqualified.append(f"{p.name}:{i}")
    check("R26: every script-emitted VERIFIED is scoped (followed by '[')",
          not unqualified, str(unqualified))

    print()
    if FAILURES:
        print(f"R24/R26: {len(FAILURES)} failure(s)")
        return 1
    print("R24/R26: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
