#!/usr/bin/env python3
"""Extract each voice's fenced JSON findings block into recall_score's
detections shape: { "<voice>": [ {file,line,category,severity,title}, ... ] }.

A voice whose output contains no parseable block is recorded in `errored`
with a reason, and excluded from detections (an errored run is not a
zero-recall run; the run README must report it separately)."""
import json
import re
import sys
from pathlib import Path

OUT_DIR = Path(sys.argv[1])
FENCE = re.compile(r"```json\s*(\[.*?\])\s*```", re.DOTALL)
REQUIRED = {"file", "line", "category", "severity", "title"}

detections: dict[str, list] = {}
errored: dict[str, str] = {}

def _candidate_texts(raw: str) -> list[str]:
    """The voice's own text, unwrapped from any transport envelope.

    OMP's eval bridge serializes a subagent that yields STRUCTURED output, so a
    voice whose agent yielded {"findings": "```json ...```"} lands on disk as a
    JSON object with the fenced block escaped inside a string value. The block is
    fully compliant; the envelope is the harness's, not the voice's. Unwrapping is
    mechanical and applied to every voice identically -- declaring such a voice
    ERRORED would measure the bridge's serialization, not adversarial fitness.
    """
    texts = [raw]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return texts
    stack = [parsed]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            texts.append(node)
        elif isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return texts


for md in sorted(OUT_DIR.glob("*.md")):
    voice = md.stem
    text = md.read_text()
    if not text.strip():
        err = (OUT_DIR / f"{voice}.err")
        reason = err.read_text().strip()[:200] if err.exists() else "empty output"
        errored[voice] = reason or "empty output"
        continue
    parsed = None
    for text_candidate in _candidate_texts(text):
        blocks = FENCE.findall(text_candidate)
        for candidate in reversed(blocks):  # last block wins if several
            try:
                data = json.loads(candidate)
                if isinstance(data, list):
                    parsed = data
                    break
            except json.JSONDecodeError:
                continue
        if parsed is not None:
            break
        # fallback: a bare JSON array with no fence around it
        try:
            data = json.loads(text_candidate.strip())
            if isinstance(data, list):
                parsed = data
                break
        except json.JSONDecodeError:
            pass
    if parsed is None:
        errored[voice] = "no parseable json findings block"
        continue
    findings = []
    dropped = 0
    for f in parsed:
        if isinstance(f, dict) and REQUIRED <= set(f) and isinstance(f.get("line"), int):
            findings.append({k: f[k] for k in ("file", "line", "category", "severity", "title")})
        else:
            dropped += 1
    detections[voice] = findings
    if dropped:
        print(f"note: {voice}: dropped {dropped} malformed finding(s)", file=sys.stderr)

result = {"detections": detections, "errored": errored}
json.dump(detections, open(OUT_DIR.parent / "detections.json", "w"), indent=2)
json.dump(errored, open(OUT_DIR.parent / "errored.json", "w"), indent=2)
for v, n in ((v, len(f)) for v, f in detections.items()):
    print(f"{v}: {n} finding(s)")
for v, r in errored.items():
    print(f"{v}: ERRORED ({r})")
