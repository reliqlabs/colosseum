#!/usr/bin/env python3
"""Stub dispatcher for tests/m3b_benchmark_runner.py.

Stands in for `opencode run`. Emits canned fenced-json findings that vary by
voice and by prompt so the arms differ and every arm's recall is
hand-computable. NO real model call. Deterministic.

Invoked as: stub_dispatch.py --model <voice> <prompt>
(the runner substitutes {model} and {prompt} into its dispatch template).

Env knobs the test sets:
  STUB_CALLS_FILE    append one line per invocation: "<voice>\\t<mode>\\t<critique>"
  STUB_PROMPTS_DIR   write the full prompt of each invocation here for inspection
  STUB_ERROR_VOICES  csv of voices that must error (exit 1, no findings)

Per-voice ground truth (matches tests/fixtures/m3b/corpus.json):
  alpha  adversarial -> D1,D2   ordinary -> D1
  beta   adversarial -> D2,D3   ordinary -> D2
  gamma  errors (in STUB_ERROR_VOICES)
In a critique prompt, the voice ADOPTS every candidate in the blinded union
(proving it consumed the round-1 findings of the others) on top of its base.
"""
import json
import os
import re
import sys

D1 = {"file": "src/a.rs", "line": 10, "category": "off-by-one",
      "severity": "high", "title": "loop admits one element too many"}
D2 = {"file": "src/a.rs", "line": 20, "category": "unchecked-arithmetic",
      "severity": "high", "title": "counter addition can overflow"}
D3 = {"file": "src/b.rs", "line": 30, "category": "invariant-violation",
      "severity": "critical", "title": "step breaks the acc/idx invariant"}

BASE_ADVERSARIAL = {"alpha": [D1, D2], "beta": [D2, D3]}
BASE_ORDINARY = {"alpha": [D1], "beta": [D2]}

FENCE = re.compile(r"```json\s*(\[.*?\])\s*```", re.DOTALL)
ORDINARY_MARK = "This is an ordinary, non-adversarial code review."
CRITIQUE_MARK = "Candidate findings from other reviewers (authorship withheld):"


def main() -> int:
    argv = sys.argv[1:]
    model = None
    for i, a in enumerate(argv):
        if a == "--model" and i + 1 < len(argv):
            model = argv[i + 1]
    prompt = argv[-1] if argv else ""

    critique = CRITIQUE_MARK in prompt
    mode = "ordinary" if (ORDINARY_MARK in prompt and not critique) else "adversarial"

    calls = os.environ.get("STUB_CALLS_FILE")
    if calls:
        with open(calls, "a") as fh:
            fh.write(f"{model}\t{mode}\t{critique}\n")
    pdir = os.environ.get("STUB_PROMPTS_DIR")
    if pdir:
        os.makedirs(pdir, exist_ok=True)
        n = len(os.listdir(pdir))
        with open(os.path.join(pdir, f"{model}.{n}.prompt"), "w") as fh:
            fh.write(prompt)

    errs = {v.strip() for v in os.environ.get("STUB_ERROR_VOICES", "").split(",") if v.strip()}
    if model in errs:
        print(f"stub: voice {model} configured to error", file=sys.stderr)
        return 1

    findings = list((BASE_ORDINARY if mode == "ordinary" else BASE_ADVERSARIAL)
                    .get(model, []))
    if critique:
        # Adopt the blinded union (the last fenced json block in the prompt).
        blocks = FENCE.findall(prompt)
        if blocks:
            try:
                union = json.loads(blocks[-1])
            except json.JSONDecodeError:
                union = []
            have = {(f["file"], f["line"], f["category"]) for f in findings}
            for f in union:
                key = (f.get("file"), f.get("line"), f.get("category"))
                if key not in have and isinstance(f, dict):
                    findings.append(f)
                    have.add(key)

    print("Stub review report.\n")
    print("```json")
    print(json.dumps(findings, indent=2))
    print("```")
    return 0


if __name__ == "__main__":
    sys.exit(main())
