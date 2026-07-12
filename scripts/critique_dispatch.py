#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
critique_dispatch — canonical template for the critique loop rounds (C3).

Promoted from the verified-rcv prototypes (cross_critique_dispatch.py,
critique_and_defense_dispatch.py, revised_canonical_critique.py) into one
config-driven template. Copy to <project>/.colosseum/scripts/ and supply a
config; the prompt builders bake in the blinding rules and the G4 framing
(near-unanimous concession prioritizes; only evidence closes).

Rounds (config `phase`):
  cross-critique  each voice reviews ANOTHER voice's artifact against the
                  Q1/Q2/Q3 protocol. The reviewer sees the target artifact,
                  its own artifact, and the intent — never another
                  reviewer's critique, never the synthesis' assessment,
                  never a prior verdict about the target.
  defense         for one contested defect claim: author voice + one
                  original critic + one independent voice each respond
                  defend / concede / propose-third-option with reasoning.
                  The prompt states G4 explicitly: concession mandates
                  priority, evidence closes.
  re-critique     the Q1/Q2/Q3 protocol re-run on a revised artifact with
                  "is the fix structurally sound / did the revision
                  introduce new defects?" prepended. Mandatory when the
                  revision touched a load-bearing predicate.

CONFIG (JSON)
    {
      "phase": "cross-critique" | "defense" | "re-critique",
      "intent_path": "<abs path>",
      "agent": "quint-spec-generator",       # opencode agent to dispatch
      "variant": "max",                      # max reasoning: default-effort
                                             # critiques miss tautological shadows
      "out_dir": "<abs path>",
      "per_call_timeout": 1800,
      "voices": [ {"id": "...", "model": "provider/model",
                   "artifact_dir": "<dir with the voice's files>",
                   "files": ["spec.qnt", "main.qnt"]} ],
      // defense phase only:
      "defense": {"axis": "<short defect axis name>",
                  "critique_quote": "<the defect claim, quoted verbatim>",
                  "critic_id": "<which voice raised it>",
                  "defender_id": "<author voice>",
                  "panel": ["defender", "critic", "independent-voice-id"]}
    }

Run each round as its own manifest run so history is legible:
    colosseum_run.py init <target> --phase critique|defense|re-critique ...

Dispatch goes through `opencode run` with --format json; the final message
is written per pair under out_dir. This is a TEMPLATE: milestone runs
should route through opencode_dispatch.py-style isolation (Z2) by running
this script against a worktree copy of the project.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

Q123_PROTOCOL = """\
## Q1. Most material structural divergence

State the single divergence you consider most material between your artifact and \
the target. Be specific: which state variable, action, or invariant differs, and \
why the difference matters for what the artifact claims. Pick one and defend it.

## Q2. Apparent defect in target

The target passes its mechanical checks, but check-clean does not mean \
intent-faithful. Identify one defect, if any: technically valid but trivially \
encoded (a tautological `true` shadow), semantically wrong, a witness whose \
negation does not express reachability, a guard admitting behaviors the intent \
forbids, or a state variable no action constrains. If you find no defect, say so \
explicitly with one sentence of reasoning.

## Q3. Change to your own artifact after reading target

Identify one concrete change you would make to YOUR artifact after seeing the \
target, or state that none is warranted, with one sentence.
"""

BLINDING_NOTE = """\
You are seeing only: the target artifact, your own artifact, and the intent. \
You are deliberately NOT shown other reviewers' critiques, any synthesis \
assessment, or any prior verdict about this target — review it fresh.
"""


def load_artifact(voice: dict) -> str:
    parts = []
    base = Path(voice["artifact_dir"])
    for name in voice["files"]:
        p = base / name
        body = p.read_text() if p.exists() else "(file missing)"
        parts.append(f"==={name}===\n{body}\n===END {name}===")
    return "\n\n".join(parts)


def cross_critique_prompt(cfg: dict, reviewer: dict, target: dict, out_path: Path,
                          revised: bool) -> str:
    prefix = ""
    if revised:
        prefix = (
            "The target artifact is a REVISION applied in response to an earlier "
            "critique round. Two questions come before the protocol below: is the "
            "fix structurally sound, and did the revision introduce NEW defects? "
            "Revision-induced regressions are the norm, not the exception.\n\n"
        )
    return f"""You are one voice in a Colosseum multi-voice critique round.

Your role this turn: REVIEW another voice's artifact as a peer reviewer. You are
NOT generating an artifact. {BLINDING_NOTE}
Your voice id: {reviewer["id"]}
Target voice id: {target["id"]}
Intent document: {cfg["intent_path"]}

{prefix}Your artifact (context; defend it only where the protocol asks):

{load_artifact(reviewer)}

Target artifact to review:

{load_artifact(target)}

You may use your tools to read the intent or run mechanical checks against the
target. Then write a structured critique to {out_path} with exactly these
sections:

# Cross-critique: {reviewer["id"]} reviews {target["id"]}

{Q123_PROTOCOL}
## Optional notes

Under 200 words.

Stop after writing the critique. Emit STATUS: ok (or STATUS: error: <reason>)
as the last line of your output."""


def defense_prompt(cfg: dict, panelist: dict, out_path: Path) -> str:
    d = cfg["defense"]
    role = ("the artifact's author" if panelist["id"] == d["defender_id"]
            else "the original critic" if panelist["id"] == d["critic_id"]
            else "an independent third voice")
    return f"""You are one voice in a Colosseum defense round, convened because a
critique round surfaced a non-trivial defect claim.

Axis under defense: {d["axis"]}
Your voice id: {panelist["id"]} (role in this panel: {role})
Intent document: {cfg["intent_path"]}

The artifact under discussion:

{load_artifact(panelist) if panelist["id"] == d["defender_id"] else load_artifact(next(v for v in cfg["voices"] if v["id"] == d["defender_id"]))}

The defect claim, verbatim:

===CRITIQUE BY {d["critic_id"]}===
{d["critique_quote"]}
===END===

Respond with exactly one of, plus reasoning grounded in intent text or a
mechanical check you ran:

A. DEFEND — concrete reasoning for why the encoding is correct; cite the intent
   where it supports you; acknowledge real limitations and why they are
   acceptable.
B. CONCEDE — the critique is correct; specify the concrete change you would make.
C. THIRD OPTION — a different encoding that addresses the concern and differs
   from what the critique implicitly proposes; justify why it beats both.

Adjudication context (contract G4): a near-unanimous concession from this panel
MANDATES the fix's priority. It does not by itself close the finding — closure
requires evidence (a counterexample, a failing or passing mechanical check, a
recorded human ruling). If your position rests on evidence, attach it.

Write your response to {out_path}. Emit STATUS: ok (or STATUS: error: <reason>)
as the last line of your output."""


async def dispatch_one(cfg: dict, voice: dict, message: str, out_dir: Path,
                       label: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prompt.md").write_text(message)
    cmd = ["opencode", "run", "--agent", cfg.get("agent", "quint-spec-generator"),
           "--model", voice["model"], "--format", "json"]
    if cfg.get("variant", "max"):
        cmd += ["--variant", cfg.get("variant", "max")]
    cmd.append(message)
    t0 = datetime.now(timezone.utc)
    print(f"→ {label} dispatching", flush=True)
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=cfg.get("per_call_timeout", 1800))
    except asyncio.TimeoutError:
        proc.kill()
        return {"label": label, "error": "timeout"}
    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    (out_dir / "events.jsonl").write_bytes(stdout)
    (out_dir / "stderr.log").write_bytes(stderr)
    ok = proc.returncode == 0
    print(f"{'✓' if ok else '✗'} {label} ({elapsed:.0f}s, exit={proc.returncode})",
          flush=True)
    return {"label": label, "elapsed_s": elapsed, "returncode": proc.returncode}


async def run(cfg: dict) -> int:
    out_root = Path(cfg["out_dir"])
    phase = cfg["phase"]
    tasks = []
    if phase in ("cross-critique", "re-critique"):
        for reviewer in cfg["voices"]:
            for target in cfg["voices"]:
                if reviewer["id"] == target["id"]:
                    continue
                pair_dir = out_root / f"{reviewer['id']}-reviews-{target['id']}"
                msg = cross_critique_prompt(
                    cfg, reviewer, target, pair_dir / "critique.md",
                    revised=(phase == "re-critique"))
                tasks.append(dispatch_one(cfg, reviewer, msg, pair_dir,
                                          f"{reviewer['id']} -> {target['id']}"))
    elif phase == "defense":
        for pid in cfg["defense"]["panel"]:
            panelist = next(v for v in cfg["voices"] if v["id"] == pid)
            pdir = out_root / f"{pid}-defense"
            msg = defense_prompt(cfg, panelist, pdir / "defense.md")
            tasks.append(dispatch_one(cfg, panelist, msg, pdir, f"defense:{pid}"))
    else:
        sys.exit(f"FATAL: unknown phase {phase!r}")

    results = await asyncio.gather(*tasks)
    failed = [r for r in results if r.get("error") or r.get("returncode")]
    print(f"\n{len(results) - len(failed)}/{len(results)} calls OK")
    return 1 if len(failed) == len(results) else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, type=Path)
    args = ap.parse_args()
    cfg = json.loads(args.config.read_text())
    return asyncio.run(run(cfg))


if __name__ == "__main__":
    sys.exit(main())
