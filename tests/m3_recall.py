#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
M3 — seeded-defect recall scorer (calibration harness half).

recall_score.py scores a set of per-voice detections against a seeded-defect
corpus (ground truth). This suite pins the math on a fixture where every
number is hand-computable, and pins the match rule (line tolerance,
category-must-match, unmatched-is-not-recall), the shared-blind-spot
computation, the findings-form input path, and the two INCOMPLETE guards
(empty corpus, snapshot mismatch).

Fixture (5 defects D1..D5; voices a/b/c):
  voice-a: D1 (exact), D4 (exact), + 1 unmatched false positive
  voice-b: D1 (2 lines off, within tol), + 1 right-place wrong-category (no D5)
  voice-c: D2, D5
  => D3 is caught by nobody: the shared blind spot.
  => panel union recall 4/5; a=2/5, b=1/5, c=2/5.

No external toolchain required. Exit 0 pass, 1 fail, 2 harness error.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "recall_score.py"
FIX = REPO / "tests" / "fixtures" / "m3"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def load_mod():
    spec = importlib.util.spec_from_file_location("recall_score", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(*args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["uv", "run", "--script", str(SCRIPT), *args],
        capture_output=True, text=True, timeout=60)
    return proc.returncode, proc.stdout, proc.stderr


def run_json(*args: str) -> tuple[int, dict]:
    rc, out, err = run(*args, "--json")
    try:
        return rc, json.loads(out)
    except json.JSONDecodeError:
        return rc, {"_stdout": out, "_stderr": err}


def approx(a: float, b: float) -> bool:
    return abs(a - b) < 1e-9


def main() -> int:
    mod = load_mod()
    corpus = FIX / "corpus.json"
    detections = FIX / "detections.json"

    # --- match rule unit checks (the crux of recall correctness) ------------
    d1 = {"file": "src/counter.rs", "line": 10, "category": "off-by-one"}
    check("exact match", mod.matches(
        {"file": "src/counter.rs", "line": 10, "category": "off-by-one"}, d1, 5))
    check("within tolerance (2 off) matches", mod.matches(
        {"file": "counter.rs", "line": 12, "category": "off-by-one"}, d1, 5))
    check("outside tolerance (6 off) does NOT match", not mod.matches(
        {"file": "src/counter.rs", "line": 16, "category": "off-by-one"}, d1, 5))
    check("wrong category does NOT match", not mod.matches(
        {"file": "src/counter.rs", "line": 10, "category": "typo"}, d1, 5))
    check("wrong file does NOT match", not mod.matches(
        {"file": "src/other.rs", "line": 10, "category": "off-by-one"}, d1, 5))
    check("basename match ignores directory", mod.matches(
        {"file": "/abs/path/counter.rs", "line": 10, "category": "OFF-BY-ONE"},
        d1, 5))

    # --- full scoring over the fixture --------------------------------------
    rc, r = run_json("--corpus", str(corpus), "--detections", str(detections))
    check("scored exit 0", rc == 0, f"rc={rc}")
    check("defect_count 5", r.get("defect_count") == 5)
    pv = r.get("per_voice", {})
    check("voice-a recall 2/5", approx(pv.get("voice-a", {}).get("recall", -1), 0.4))
    check("voice-b recall 1/5 (wrong-category near-miss excluded)",
          approx(pv.get("voice-b", {}).get("recall", -1), 0.2))
    check("voice-c recall 2/5", approx(pv.get("voice-c", {}).get("recall", -1), 0.4))
    check("voice-a caught D1,D4",
          pv.get("voice-a", {}).get("caught") == ["D1", "D4"])
    check("voice-b caught only D1",
          pv.get("voice-b", {}).get("caught") == ["D1"])
    check("voice-a has 1 unmatched detection (false positive)",
          pv.get("voice-a", {}).get("unmatched_detections") == 1)
    check("voice-b has 1 unmatched detection (wrong-category hit)",
          pv.get("voice-b", {}).get("unmatched_detections") == 1)
    check("shared blind spot is exactly [D3]",
          r.get("shared_blind_spot") == ["D3"])
    check("shared_blind_spot_count 1", r.get("shared_blind_spot_count") == 1)
    check("panel union recall 4/5", approx(r.get("panel_union_recall", -1), 0.8))
    check("D1 credited to both a and b",
          r.get("caught_by", {}).get("D1") == ["voice-a", "voice-b"])
    check("D3 credited to nobody",
          r.get("caught_by", {}).get("D3") == [])
    check("no precision number is emitted (only unmatched counts)",
          "precision" not in json.dumps(r).lower() or "not computed" in
          r.get("unmatched_note", ""))

    # --- findings-form input path (confirmed[] + sources[]) ------------------
    findings = FIX / "findings-form.json"
    rc, rf = run_json("--corpus", str(corpus), "--detections", str(findings))
    check("findings-form scored exit 0", rc == 0)
    pvf = rf.get("per_voice", {})
    check("findings-form: D1 credited to a and b via sources[]",
          rf.get("caught_by", {}).get("D1") == ["voice-a", "voice-b"])
    check("findings-form: voice-c caught D2",
          pvf.get("voice-c", {}).get("caught") == ["D2"])

    # --- INCOMPLETE guards ---------------------------------------------------
    rc, _, err = run("--corpus", str(FIX / "corpus-empty.json"),
                     "--detections", str(detections))
    check("empty corpus -> exit 3 INCOMPLETE",
          rc == 3 and "INCOMPLETE" in err, f"rc={rc}")

    rc, _, err = run("--corpus", str(corpus), "--detections", str(detections),
                     "--expect-snapshot", "zzzznope")
    check("snapshot mismatch -> exit 3 INCOMPLETE",
          rc == 3 and "INCOMPLETE" in err, f"rc={rc}")
    with tempfile.TemporaryDirectory(prefix="m3-schema-") as td:
        invalid = Path(td) / "corpus.json"
        payload = json.loads(corpus.read_text())
        payload["schema"] = "fv-seeded-corpus/v999"
        invalid.write_text(json.dumps(payload))
        rc, _, err = run("--corpus", str(invalid), "--detections", str(detections))
        check("non-v2 corpus schema -> exit 2 error",
              rc == 2 and "unsupported corpus schema" in err, f"rc={rc} err={err}")

    rc, _, err = run("--corpus", str(corpus), "--detections", str(detections),
                     "--expect-snapshot", "abc1234")
    check("matching snapshot prefix -> exit 0",
          rc == 0, f"rc={rc} err={err}")

    print()
    if FAILURES:
        print(f"M3: {len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        return 1
    print("M3: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
