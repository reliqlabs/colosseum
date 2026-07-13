#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
recall_score — seeded-defect recall per voice (roadmap M3, harness half).

Given a seeded-defect corpus (KNOWN planted flaws, ground truth) and a set
of per-voice detections, compute how many seeded defects each voice caught,
which defects NO voice caught (the shared blind spot, the direct measure of
shared-blind-spot risk), and the panel/union recall. This is the scoring
machinery for the prospective benchmark in docs/benchmark-protocol.md. The
benchmark RUN itself needs live multi-model dispatch and has NOT been
executed; this tool computes recall over whatever corpus + detections it is
given and invents nothing.

CORPUS (templates/seeded-defect-corpus.example.json; schema
colosseum-seeded-corpus/v1)
    { "schema": "...", "target": "...", "target_snapshot": "<commit>+<hash>",
      "line_tolerance": 5,
      "defects": [ {"id","file","line","category","severity",
                    "detection_key", ...}, ... ] }

DETECTIONS (--detections)
    { "<voice_id>": [ {"file","line","category","title"?}, ... ], ... }
    A findings-JSON object with a top-level "confirmed" list is also
    accepted: each finding's `sources` entries become the crediting voices.

MATCH RULE (documented in docs/benchmark-protocol.md)
    A detection matches seeded defect D iff
      basename(detection.file) == basename(D.file)  AND
      detection.category.strip().lower() == D.category.strip().lower()  AND
      abs(detection.line - D.line) <= line_tolerance
    A right-place wrong-category hit does NOT count as recall. A detection
    matching no seeded defect is an unmatched detection (candidate false
    positive), counted but never turned into a precision number unless
    ground-truth labels are supplied (out of scope here).

VERDICT / EXIT
    0  scored
    2  usage/read error
    3  INCOMPLETE — empty corpus, or --expect-snapshot mismatch (cannot
       score recall against a corpus that does not describe the target run)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def basename(p: str) -> str:
    return os.path.basename(str(p))


def load_detections(data: object) -> dict[str, list[dict]]:
    """Accept either a {voice: [detections]} map or a findings object with a
    `confirmed` list whose findings carry `sources`."""
    if isinstance(data, dict) and "confirmed" in data and \
            isinstance(data["confirmed"], list):
        out: dict[str, list[dict]] = {}
        for f in data["confirmed"]:
            det = {"file": f.get("file"), "line": f.get("line"),
                   "category": f.get("category") or f.get("kind"),
                   "title": f.get("title")}
            for voice in (f.get("sources") or ["<unattributed>"]):
                out.setdefault(voice, []).append(det)
        return out
    if isinstance(data, dict):
        return {v: list(dets) for v, dets in data.items()}
    raise ValueError("detections must be a {voice: [..]} map or a findings "
                     "object with a 'confirmed' list")


def matches(det: dict, defect: dict, tol: int) -> bool:
    try:
        if basename(det.get("file", "")) != basename(defect["file"]):
            return False
        dc = str(det.get("category", "")).strip().lower()
        if dc != str(defect["category"]).strip().lower():
            return False
        return abs(int(det.get("line", -10**9)) - int(defect["line"])) <= tol
    except (TypeError, ValueError):
        return False


def score(corpus: dict, detections: dict[str, list[dict]]) -> dict:
    tol = int(corpus.get("line_tolerance", 5))
    defects = corpus["defects"]
    n = len(defects)
    voices = sorted(detections)

    caught_by: dict[str, list[str]] = {d["id"]: [] for d in defects}
    per_voice_hits: dict[str, set[str]] = {v: set() for v in voices}
    unmatched: dict[str, int] = {v: 0 for v in voices}

    for voice in voices:
        for det in detections[voice]:
            hit_ids = [d["id"] for d in defects if matches(det, d, tol)]
            if hit_ids:
                for did in hit_ids:
                    caught_by[did].append(voice)
                    per_voice_hits[voice].add(did)
            else:
                unmatched[voice] += 1

    blind_spot = sorted(did for did, vs in caught_by.items() if not vs)
    union_caught = [did for did, vs in caught_by.items() if vs]

    per_voice = {
        v: {
            "recall": (len(per_voice_hits[v]) / n) if n else 0.0,
            "caught": sorted(per_voice_hits[v]),
            "unmatched_detections": unmatched[v],
        }
        for v in voices
    }
    return {
        "target": corpus.get("target"),
        "target_snapshot": corpus.get("target_snapshot"),
        "line_tolerance": tol,
        "defect_count": n,
        "voices": voices,
        "per_voice": per_voice,
        "shared_blind_spot": blind_spot,
        "shared_blind_spot_count": len(blind_spot),
        "panel_union_recall": (len(union_caught) / n) if n else 0.0,
        "caught_by": {k: sorted(set(v)) for k, v in caught_by.items()},
        "unmatched_note": "unmatched detections are candidate false positives; "
                          "precision is not computed without ground-truth labels",
    }


def render_text(r: dict) -> str:
    lines = [
        f"seeded-defect recall over {r['defect_count']} planted defect(s) "
        f"(target={r['target']}, line_tolerance={r['line_tolerance']})",
        "",
        f"{'VOICE':<20} {'RECALL':>7}  CAUGHT / UNMATCHED",
    ]
    for v in r["voices"]:
        pv = r["per_voice"][v]
        lines.append(f"{v:<20} {pv['recall']*100:>6.0f}%  "
                     f"{','.join(pv['caught']) or '-'} / "
                     f"{pv['unmatched_detections']} unmatched")
    lines.append("")
    lines.append(f"panel union recall: {r['panel_union_recall']*100:.0f}% "
                 f"({r['defect_count'] - r['shared_blind_spot_count']}"
                 f"/{r['defect_count']})")
    lines.append(f"shared blind spot ({r['shared_blind_spot_count']}): "
                 f"{', '.join(r['shared_blind_spot']) or 'none'}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--detections", required=True, type=Path)
    ap.add_argument("--expect-snapshot", default=None,
                    help="require corpus.target_snapshot to start with this")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        corpus = json.loads(args.corpus.read_text())
        det_data = json.loads(args.detections.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot read input: {e}", file=sys.stderr)
        return 2

    if not isinstance(corpus, dict) or "defects" not in corpus:
        print("error: corpus must be an object with a 'defects' list",
              file=sys.stderr)
        return 2
    if not corpus["defects"]:
        print("INCOMPLETE: corpus has zero seeded defects; recall is undefined",
              file=sys.stderr)
        return 3
    snap = corpus.get("target_snapshot", "")
    if args.expect_snapshot and not str(snap).startswith(args.expect_snapshot):
        print(f"INCOMPLETE: corpus snapshot {snap!r} does not match expected "
              f"{args.expect_snapshot!r}; refusing to score against the wrong "
              f"target", file=sys.stderr)
        return 3

    try:
        detections = load_detections(det_data)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    result = score(corpus, detections)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_text(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
