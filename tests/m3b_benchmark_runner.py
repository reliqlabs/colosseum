#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
M3b: the pre-registered ablation-arm runner (scripts/benchmark_run.py).

Drives benchmark_run.py end-to-end through a STUB dispatcher (a tiny Python
executable that emits canned fenced-json findings varying by voice and prompt)
so every arm runs offline with hand-computable recall. No real model call.

Fixture panel (voices alpha/beta/gamma; corpus D1..D4; gamma always errors):
  alpha adversarial -> D1,D2  ordinary -> D1
  beta  adversarial -> D2,D3  ordinary -> D2
  gamma -> errored (excluded from recall, logged)
  => D4 is caught by nobody: the shared blind spot in every arm.

Asserts:
  - dry-run prints the right per-arm plan and dispatches NOTHING;
  - each arm issues the right number of dispatch calls (stub side-effect file
    + summary.json agree): ordinary 1, single 1, repeated 3, multi 3, adv 6;
  - the adversarial critique round shows each voice the OTHER voices' round-1
    findings, blinded (no voice ids), and round-2 outputs differ from round 1
    and are scored separately;
  - detections parse and recall_score yields per-arm recall
    (ordinary 0.25, single 0.5, multi/adv union 0.75, D4 the shared blind spot);
  - the errored voice lands in the error log and NOT in recall denominators;
  - a missing dispatch binary and an all-errored arm both exit 3 INCOMPLETE,
    never a fake pass.

Exit 0 pass, 1 fail, 2 harness error.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "scripts" / "benchmark_run.py"
FIX = REPO / "tests" / "fixtures" / "m3b"
STUB = FIX / "stub_dispatch.py"
CORPUS = FIX / "corpus.json"
TARGETS = FIX / "target"
TEMPLATE = f"python3 {STUB} --model {{model}} {{prompt}}"

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def run(out: Path, *extra: str, voices: str = "alpha,beta,gamma",
        arms: str | None = None, template: str = TEMPLATE,
        env_extra: dict | None = None, calls: Path | None = None,
        prompts: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["STUB_ERROR_VOICES"] = "gamma"
    if calls is not None:
        env["STUB_CALLS_FILE"] = str(calls)
    if prompts is not None:
        env["STUB_PROMPTS_DIR"] = str(prompts)
    if env_extra:
        env.update(env_extra)
    cmd = ["uv", "run", "--script", str(RUNNER),
           "--corpus", str(CORPUS), "--targets", str(TARGETS),
           "--out", str(out), "--voices", voices,
           "--dispatch-cmd", template]
    if arms:
        cmd += ["--arms", arms]
    cmd += list(extra)
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300)


def load(p: Path) -> dict:
    return json.loads(p.read_text())


def recall_of(out: Path, arm: str, voice: str) -> float:
    r = load(out / arm / "recall.json")
    return r["per_voice"].get(voice, {}).get("recall", -1.0)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="m3b-") as td:
        tmp = Path(td)

        # ── dry-run: plan only, no dispatch ────────────────────────────
        calls = tmp / "dry-calls.txt"
        r = run(tmp / "dry-out", "--dry-run", calls=calls)
        check("dry-run exits 0", r.returncode == 0, f"rc={r.returncode} {r.stderr[-300:]}")
        lines = [ln for ln in r.stdout.splitlines() if ln.startswith("DRY arm=")]

        def count(pred) -> int:
            return sum(1 for ln in lines if pred(ln))
        check("dry-run plan: ordinary 1 dispatch",
              count(lambda l: "arm=ordinary " in l) == 1)
        check("dry-run plan: single 1 dispatch",
              count(lambda l: "arm=single " in l) == 1)
        check("dry-run plan: repeated 3 dispatches",
              count(lambda l: "arm=repeated " in l) == 3)
        check("dry-run plan: multi-family 3 dispatches",
              count(lambda l: "arm=multi-family " in l) == 3)
        check("dry-run plan: adversarial 6 dispatches (3 round1 + 3 round2)",
              count(lambda l: "arm=adversarial " in l) == 6 and
              count(lambda l: "arm=adversarial " in l and "round=2" in l) == 3)
        check("dry-run dispatched nothing (no stub side effects)",
              not calls.exists(),
              "stub calls file was created during a dry run")

        # ── full run through the stub ──────────────────────────────────
        out = tmp / "out"
        calls = tmp / "calls.txt"
        prompts = tmp / "prompts"
        r = run(out, calls=calls, prompts=prompts)
        check("full run exits 0", r.returncode == 0,
              f"rc={r.returncode} stderr={r.stderr[-400:]}")
        summ = load(out / "summary.json")
        check("summary verdict COMPLETE", summ.get("verdict") == "COMPLETE",
              summ.get("verdict"))

        # dispatch counts, via summary.json and the stub side-effect file.
        counts = {a: summ["arms"][a]["dispatches"] for a in summ["arms"]}
        check("dispatch counts per arm (1/1/3/3/6)",
              counts == {"ordinary": 1, "single": 1, "repeated": 3,
                         "multi-family": 3, "adversarial": 6}, str(counts))
        total_calls = len(calls.read_text().splitlines())
        check("stub saw 14 total dispatch calls", total_calls == 14, f"n={total_calls}")

        # per-arm recall (hand-computable).
        check("ordinary recall: alpha 0.25 (D1 only, neutral prompt)",
              abs(recall_of(out, "ordinary", "alpha") - 0.25) < 1e-9)
        check("single recall: alpha 0.5 (D1,D2, adversarial prompt)",
              abs(recall_of(out, "single", "alpha") - 0.5) < 1e-9)
        check("ordinary and single differ (framing matters)",
              recall_of(out, "ordinary", "alpha") != recall_of(out, "single", "alpha"))

        # repeated: three passes kept separate + a union.
        rep = load(out / "repeated" / "recall.json")
        rep_keys = set(rep["per_voice"])
        check("repeated keys each pass separately",
              rep_keys == {"alpha#pass1", "alpha#pass2", "alpha#pass3"}, str(rep_keys))
        check("repeated each pass recall 0.5",
              all(abs(rep["per_voice"][k]["recall"] - 0.5) < 1e-9 for k in rep_keys))
        check("repeated panel union recall 0.5",
              abs(rep["panel_union_recall"] - 0.5) < 1e-9)

        # multi-family: panel union, errored gamma excluded, D4 blind spot.
        mf = load(out / "multi-family" / "recall.json")
        check("multi-family per-voice recall 0.5 each",
              abs(mf["per_voice"]["alpha"]["recall"] - 0.5) < 1e-9 and
              abs(mf["per_voice"]["beta"]["recall"] - 0.5) < 1e-9)
        check("multi-family union recall 0.75",
              abs(mf["panel_union_recall"] - 0.75) < 1e-9)
        check("multi-family shared blind spot is exactly [D4]",
              mf["shared_blind_spot"] == ["D4"], str(mf["shared_blind_spot"]))
        check("errored gamma NOT a scored voice (not in denominators)",
              "gamma" not in mf["per_voice"])
        check("multi-family arm records gamma as errored",
              "gamma" in summ["arms"]["multi-family"]["errored"])

        # detections.json parses.
        det = load(out / "multi-family" / "detections.json")
        check("multi-family detections.json parses to alpha/beta findings",
              set(det) == {"alpha", "beta"} and
              all(isinstance(v, list) for v in det.values()), str(set(det)))

        # ── adversarial critique round: blinding + round separation ─────
        r1 = load(out / "adversarial" / "detections.round1.json")
        r2 = load(out / "adversarial" / "detections.json")
        adv = load(out / "adversarial" / "recall.json")
        check("adversarial round1 alpha caught D1,D2 (2 findings)",
              len(r1.get("alpha", [])) == 2)
        check("adversarial round2 differs from round1 (alpha grew to 3)",
              len(r2.get("alpha", [])) == 3 and len(r1.get("alpha", [])) == 2,
              f"r1={len(r1.get('alpha', []))} r2={len(r2.get('alpha', []))}")
        check("adversarial round2 alpha recall 0.75 (adopted the blinded union)",
              abs(adv["per_voice"]["alpha"]["recall"] - 0.75) < 1e-9)

        crit = (out / "adversarial" / "critique" / "alpha.prompt").read_text()
        # the union block alpha saw = beta's round-1 findings only.
        import re
        blocks = re.findall(r"```json\s*(\[.*?\])\s*```", crit, re.DOTALL)
        union = json.loads(blocks[-1]) if blocks else []
        union_keys = {(f["file"], f["line"], f["category"]) for f in union}
        check("critique union shows beta's D3 (b.rs:30 invariant-violation)",
              ("src/b.rs", 30, "invariant-violation") in union_keys, str(union_keys))
        check("critique union excludes alpha's OWN D1 (off-by-one a.rs:10)",
              ("src/a.rs", 10, "off-by-one") not in union_keys)
        check("critique prompt is authorship-blinded (no voice ids present)",
              not any(v in crit for v in ("alpha", "beta", "gamma")))

        # error log carries the errored voice; not scored as zero anywhere.
        elog = summ["error_log"]
        gamma_hits = [e for e in elog if "gamma" in e["key"]]
        check("error log records the errored voice across arms",
              len(gamma_hits) >= 2 and all(e["reason"] for e in gamma_hits),
              f"{len(gamma_hits)} entries")

        # cost placeholders present and null (never invented).
        check("cost/token fields are null placeholders",
              summ["arms"]["single"]["tokens"] is None and
              summ["arms"]["single"]["cost_per_confirmed_defect"] is None)

        # ── INCOMPLETE: dispatcher binary missing ──────────────────────
        r = run(tmp / "missing-out", arms="ordinary",
                template="/nonexistent/xyz-dispatch --model {model} {prompt}")
        check("missing dispatch binary -> exit 3 INCOMPLETE",
              r.returncode == 3 and "INCOMPLETE" in (r.stdout + r.stderr),
              f"rc={r.returncode}")

        # ── INCOMPLETE: an arm with zero successful dispatches ─────────
        r = run(tmp / "allerr-out", voices="gamma", arms="single")
        check("all-errored arm -> exit 3 INCOMPLETE (no fake 0.0)",
              r.returncode == 3 and "INCOMPLETE" in (r.stdout + r.stderr),
              f"rc={r.returncode}")
        allerr = load(tmp / "allerr-out" / "summary.json")
        check("all-errored arm did not write a misleading recall",
              not (tmp / "allerr-out" / "single" / "recall.json").exists() and
              allerr["arms"]["single"]["status"] == "INCOMPLETE")

    print()
    if FAILURES:
        print(f"M3b: {len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        return 1
    print("M3b: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
