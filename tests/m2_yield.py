#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
M2 self-measurement test.

Drives scripts/self_measure.py over synthetic fixtures whose math is fixed:

  voice A raises f1,f2,f3 (solo, confirmed) and f4 (shared with B, refuted).
  voice B raises f4 (shared, refuted) and f5 (solo, confirmed).

  Shared finding f4 splits 1/2 to each source. So:
    A: total_attr 3.5, confirmed_attr 3.0, yield 3.0/3.5 = 0.8571
    B: total_attr 1.5, confirmed_attr 1.0, yield 1.0/1.5 = 0.6667
    totals: 4 confirmed, 1 refuted.

Asserts yield math, severity buckets, cost (measured and unmeasured),
routing fraction, and that routing without a layer-map is INCOMPLETE (3).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures" / "m2"
SCRIPT = HERE.parent / "scripts" / "self_measure.py"

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print(f"  ok: {msg}")


def run(args: list[str]) -> tuple[int, dict | None]:
    proc = subprocess.run(["uv", "run", "--script", str(SCRIPT), *args],
                          capture_output=True, text=True)
    data = None
    if proc.stdout.strip():
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            data = None
    return proc.returncode, data


def approx(a: float, b: float, eps: float = 1e-3) -> bool:
    return abs(a - b) <= eps


def main() -> int:
    print("== yield ==")
    code, r = run(["yield", "--findings", str(FIX / "findings.json"),
                   "--run", str(FIX / "run.json"), "--json"])
    check(code == 0, f"yield exits 0 (got {code})")
    check(r is not None, "yield emits JSON")
    if r:
        check(r["phase"] == "attack", "phase read from run.json")
        check(r["totals"] == {"confirmed": 4, "refuted": 1},
              f"totals 4/1 (got {r['totals']})")
        a = r["per_voice"]["A"]
        b = r["per_voice"]["B"]
        check(a["raised_any"] == 4, f"A raised_any 4 (got {a['raised_any']})")
        check(b["raised_any"] == 2, f"B raised_any 2 (got {b['raised_any']})")
        check(approx(a["total_attr"], 3.5), f"A total_attr 3.5 (got {a['total_attr']})")
        check(approx(a["confirmed_attr"], 3.0),
              f"A confirmed_attr 3.0 (got {a['confirmed_attr']})")
        check(approx(a["yield"], 0.8571), f"A yield 0.8571 (got {a['yield']})")
        check(approx(b["total_attr"], 1.5), f"B total_attr 1.5 (got {b['total_attr']})")
        check(approx(b["yield"], 0.6667), f"B yield 0.6667 (got {b['yield']})")
        # shared finding f4 (high, refuted) splits: A high total_attr = 1(f1)+0.5(f4)=1.5
        check(approx(a["by_severity"]["high"]["total_attr"], 1.5),
              f"A high total_attr 1.5 (got {a['by_severity']['high']['total_attr']})")
        check(approx(a["by_severity"]["high"]["confirmed_attr"], 1.0),
              "A high confirmed_attr 1.0")

    print("== yield on empty adjudication -> INCOMPLETE ==")
    empty = FIX / "findings-empty.json"
    empty.write_text(json.dumps({"confirmed": [], "refuted": []}))
    code, _ = run(["yield", "--findings", str(empty), "--json"])
    check(code == 3, f"empty adjudication INCOMPLETE exit 3 (got {code})")

    print("== cost (measured) ==")
    code, r = run(["cost", "--events", str(FIX / "events.json"),
                   "--findings", str(FIX / "findings.json"), "--json"])
    check(code == 0, f"cost exits 0 (got {code})")
    if r:
        pa = r["per_voice"]["A"]
        pb = r["per_voice"]["B"]
        check(pa["tokens"] == 12000, "A tokens 12000")
        check(approx(pa["cost_per_confirmed"], 4000.0),
              f"A cost/confirmed 4000 (got {pa['cost_per_confirmed']})")
        check(approx(pb["cost_per_confirmed"], 6000.0),
              f"B cost/confirmed 6000 (got {pb['cost_per_confirmed']})")

    print("== cost (unmeasured token data) ==")
    code, r = run(["cost", "--events", str(FIX / "events-notokens.json"), "--json"])
    check(code == 0, f"cost exits 0 (got {code})")
    if r:
        check(r["per_voice"]["B"]["tokens"] == "unmeasured",
              "B tokens unmeasured, never 0")

    print("== routing (with layer-map) ==")
    code, r = run(["routing", "--findings", str(FIX / "findings.json"),
                   "--layer-map", str(FIX / "layer-map.json"), "--json"])
    check(code == 0, f"routing exits 0 (got {code})")
    if r:
        check(approx(r["routing_fraction"], 0.75),
              f"routing fraction 0.75 (got {r['routing_fraction']})")
        check(r["routing_misses"] == ["d3"],
              f"routing miss is d3 (got {r['routing_misses']})")

    print("== routing without layer-map -> INCOMPLETE ==")
    code, _ = run(["routing", "--findings", str(FIX / "findings.json"), "--json"])
    check(code == 3, f"routing without layer-map INCOMPLETE exit 3 (got {code})")

    print("== routing with incomplete layer-map -> INCOMPLETE ==")
    code, _ = run(["routing", "--layer-map", str(FIX / "layer-map-incomplete.json"),
                   "--json"])
    check(code == 3, f"incomplete layer-map INCOMPLETE exit 3 (got {code})")

    empty.unlink(missing_ok=True)
    print()
    if failures:
        print(f"M2 FAILED ({len(failures)} check(s))")
        return 1
    print("M2 PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
