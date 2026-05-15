#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
colosseum-run — harness-agnostic dispatch manifest for multi-model adversarial passes.

The manifest pattern lets multiple harnesses (Claude Code, OpenCode, plain shell)
coordinate on a shared adversarial-review run without any in-process coupling.
Each harness reads + updates the same `run.json` file in the run directory;
the manifest IS the state machine.

USAGE

    # Phase 1: orchestrator (any harness or human) creates the manifest:
    colosseum_run.py init <target-spec.md> \
        --voices=claude,kimi-k2-6,glm-4-7-flash,gpt-oss-120b \
        --owners=claude:claude-code,kimi-k2-6:opencode,glm-4-7-flash:opencode,gpt-oss-120b:opencode

    # Phase 2: each harness dispatches its assigned voices, writes the per-voice file,
    # and marks the manifest entry complete (or errored):
    colosseum_run.py complete <run-dir> --voice=claude --elapsed=339 --finish-reason=stop
    colosseum_run.py error    <run-dir> --voice=kimi-k2-6 --detail="HTTP 408 at 240s" --elapsed=239

    # Inspection:
    colosseum_run.py status <run-dir>          # human-readable table
    colosseum_run.py status <run-dir> --json   # machine-readable manifest

    # Re-run a voice (flips status back to pending):
    colosseum_run.py reset <run-dir> --voice=kimi-k2-6

    # Build the synthesis prompt body (deterministic, no LLM call). Concatenates
    # per-voice files into one document with a structural-overlap header:
    colosseum_run.py synthesize <run-dir> --out=synthesis-input.md

    # Wait for all voices to land (blocking, no LLM call). Exits 0 on completion,
    # 1 on timeout. Useful inside a `make` rule or shell pipeline:
    colosseum_run.py wait <run-dir> --timeout=3600

MANIFEST SCHEMA

    {
      "run_id":  "<basename>-<ISO-UTC-timestamp>",
      "target":  "<path/to/spec-under-review>",
      "created": "<ISO-UTC-timestamp>",
      "voices": [
        {
          "id":            "<voice-id>",            // unique within the run
          "harness":       "<claude-code|opencode|shell|...>",
          "file":          "<path relative to run-dir>",
          "status":        "<pending|complete|error|skipped>",
          "elapsed_s":     <number>,                // optional, set on completion
          "finish_reason": "<stop|length|tool_use|error>", // optional
          "error_detail":  "<string>",              // optional, set on error
          "metadata":      { "<key>": "<value>" }   // optional, harness-specific
        },
        ...
      ],
      "synthesis": {
        "file":    "synthesis.md",
        "harness": "claude-code",
        "status":  "pending"
      }
    }
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# -----------------------------------------------------------------------------
# Manifest I/O
# -----------------------------------------------------------------------------

MANIFEST_NAME = "run.json"

def manifest_path(run_dir: Path) -> Path:
    return run_dir / MANIFEST_NAME


def load_manifest(run_dir: Path) -> dict[str, Any]:
    p = manifest_path(run_dir)
    if not p.exists():
        sys.exit(f"error: no {MANIFEST_NAME} at {p}")
    with p.open() as f:
        return json.load(f)


def save_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    # Round-trip via temp file → atomic rename so concurrent readers never
    # observe a half-written manifest.
    p = manifest_path(run_dir)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    tmp.replace(p)


def find_voice(manifest: dict[str, Any], voice_id: str) -> dict[str, Any]:
    for v in manifest["voices"]:
        if v["id"] == voice_id:
            return v
    sys.exit(f"error: voice {voice_id!r} not in manifest (have: {[v['id'] for v in manifest['voices']]})")


# -----------------------------------------------------------------------------
# init
# -----------------------------------------------------------------------------

def parse_owners(s: str) -> dict[str, str]:
    """Parse `--owners=voice1:harness1,voice2:harness2` into a dict."""
    out = {}
    for part in s.split(","):
        if not part.strip():
            continue
        if ":" not in part:
            sys.exit(f"error: bad --owners segment {part!r}; expected `voice:harness`")
        k, v = part.split(":", 1)
        out[k.strip()] = v.strip()
    return out


def slug_for_voice(voice_id: str, harness: str) -> str:
    safe = voice_id.replace("/", "-").replace(":", "-")
    prefix = harness if harness in {"claude-code", "opencode"} else harness
    if voice_id == "claude" and harness == "claude-code":
        return "claude.md"
    return f"{prefix}-{safe}.md"


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve()
    if not target.exists():
        sys.exit(f"error: target {target} does not exist")

    voice_ids = [v.strip() for v in args.voices.split(",") if v.strip()]
    owners = parse_owners(args.owners) if args.owners else {}

    for v in voice_ids:
        if v not in owners:
            sys.exit(f"error: voice {v!r} has no owner; pass --owners={v}:<harness>")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    basename = target.stem
    run_id = f"{basename}-{now}"

    if args.run_dir:
        run_dir = Path(args.run_dir).resolve()
    else:
        # Default: <target's project>/.colosseum/attacks/<run-id>/
        # Walk up from target looking for .colosseum, fall back to target parent.
        parent = target.parent
        while parent != parent.parent:
            if (parent / ".colosseum").is_dir():
                break
            parent = parent.parent
        if (parent / ".colosseum").is_dir():
            run_dir = parent / ".colosseum" / "attacks" / run_id
        else:
            run_dir = target.parent / f"attacks-{run_id}"

    run_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "run_id":  run_id,
        "target":  str(target),
        "created": now,
        "voices": [],
        "synthesis": {
            "file":    "synthesis.md",
            "harness": args.synthesis_harness,
            "status":  "pending",
        },
    }
    for vid in voice_ids:
        harness = owners[vid]
        manifest["voices"].append({
            "id":      vid,
            "harness": harness,
            "file":    slug_for_voice(vid, harness),
            "status":  "pending",
        })

    save_manifest(run_dir, manifest)
    print(f"created run dir: {run_dir}")
    print(f"manifest:        {manifest_path(run_dir)}")
    print(f"voices:          {len(voice_ids)} ({', '.join(voice_ids)})")
    return 0


# -----------------------------------------------------------------------------
# status
# -----------------------------------------------------------------------------

def _status_emoji(s: str) -> str:
    return {"pending": "○", "complete": "✓", "error": "✗", "skipped": "—"}.get(s, "?")


def cmd_status(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = load_manifest(run_dir)

    if args.json:
        print(json.dumps(manifest, indent=2))
    else:
        print(f"run_id: {manifest['run_id']}")
        print(f"target: {manifest['target']}")
        print()
        print(f"  {'voice':30s}  {'harness':12s}  {'status':8s}  {'elapsed':>9s}  {'finish':10s}  file")
        print(f"  {'-'*30}  {'-'*12}  {'-'*8}  {'-'*9}  {'-'*10}  {'-'*40}")
        for v in manifest["voices"]:
            elapsed = f"{v.get('elapsed_s', 0):.1f}s" if v.get("elapsed_s") is not None else "-"
            finish = v.get("finish_reason") or "-"
            print(f"  {_status_emoji(v['status'])} {v['id']:28s}  {v['harness']:12s}  {v['status']:8s}  {elapsed:>9s}  {finish:10s}  {v['file']}")
        syn = manifest["synthesis"]
        print()
        print(f"  {_status_emoji(syn['status'])} synthesis ({syn['harness']:12s}, {syn['status']:8s})           file: {syn['file']}")

    # Exit codes are useful for scripted use:
    statuses = {v["status"] for v in manifest["voices"]}
    if "error" in statuses:
        return 2
    if "pending" in statuses:
        return 1
    return 0


# -----------------------------------------------------------------------------
# complete / error / reset
# -----------------------------------------------------------------------------

def cmd_complete(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = load_manifest(run_dir)
    voice = find_voice(manifest, args.voice)

    file_path = run_dir / voice["file"]
    if not file_path.exists():
        sys.exit(f"error: voice file {file_path} does not exist; write it before marking complete")

    voice["status"] = "complete"
    if args.elapsed is not None:
        voice["elapsed_s"] = args.elapsed
    if args.finish_reason:
        voice["finish_reason"] = args.finish_reason
    voice.pop("error_detail", None)
    save_manifest(run_dir, manifest)
    print(f"marked {args.voice} complete ({file_path})")
    return 0


def cmd_error(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = load_manifest(run_dir)
    voice = find_voice(manifest, args.voice)

    voice["status"] = "error"
    voice["error_detail"] = args.detail
    if args.elapsed is not None:
        voice["elapsed_s"] = args.elapsed
    save_manifest(run_dir, manifest)
    print(f"marked {args.voice} error: {args.detail}")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = load_manifest(run_dir)
    voice = find_voice(manifest, args.voice)

    voice["status"] = "pending"
    voice.pop("elapsed_s", None)
    voice.pop("finish_reason", None)
    voice.pop("error_detail", None)
    save_manifest(run_dir, manifest)
    print(f"reset {args.voice} to pending")
    return 0


# -----------------------------------------------------------------------------
# wait
# -----------------------------------------------------------------------------

def cmd_wait(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    deadline = time.monotonic() + args.timeout
    poll = max(2.0, min(args.poll, args.timeout))
    while time.monotonic() < deadline:
        manifest = load_manifest(run_dir)
        statuses = {v["status"] for v in manifest["voices"]}
        if "pending" not in statuses:
            counts = {s: sum(1 for v in manifest["voices"] if v["status"] == s) for s in ["complete", "error", "skipped"]}
            print(f"done: {counts}")
            return 0
        pending = [v["id"] for v in manifest["voices"] if v["status"] == "pending"]
        print(f"  waiting on {len(pending)} pending: {', '.join(pending)} (sleep {poll:.0f}s)")
        time.sleep(poll)
    print(f"timeout after {args.timeout}s")
    return 1


# -----------------------------------------------------------------------------
# synthesize (build prompt body; no LLM call)
# -----------------------------------------------------------------------------

VERDICT_INLINE_RE = re.compile(r"VERDICT[:\s]+([A-Za-z\- ]+(?:\s*\([^)]*\))?)", re.IGNORECASE)
VERDICT_HEADER_RE = re.compile(r"^#+\s*VERDICT\s*$", re.IGNORECASE | re.MULTILINE)
VERDICT_KEYWORD_RE = re.compile(r"\b(BREAKS\-?AGAIN|BREAKS|SURVIVES|INDETERMINATE)\b", re.IGNORECASE)


def _is_template_echo(s: str) -> bool:
    """The 'BREAKS | SURVIVES | INDETERMINATE' menu the model copied from the prompt."""
    u = s.upper()
    return "|" in s and "SURVIVES" in u and "BREAKS" in u


def extract_verdict(content: str) -> str:
    """Pull a VERDICT out of a voice's report.

    Three shapes we accept (in priority order, scanning from the end):
      (a) inline       — `VERDICT: BREAKS-AGAIN (reason)`
      (b) two-line     — `## VERDICT\n\nBREAKS-AGAIN`
      (c) bare keyword — last non-template occurrence of BREAKS/SURVIVES/INDETERMINATE
    """
    # (a) inline form, scanning bottom-up
    for line in reversed(content.splitlines()):
        m = VERDICT_INLINE_RE.search(line)
        if m:
            verdict = m.group(1).strip()
            if _is_template_echo(verdict):
                continue
            return verdict

    # (b) two-line form — find `## VERDICT` header, return the first
    # non-blank line after it
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if VERDICT_HEADER_RE.match(line):
            for follow in lines[i + 1:]:
                stripped = follow.strip()
                if stripped and not _is_template_echo(stripped):
                    # Trim trailing punctuation / surrounding markdown
                    return stripped.lstrip("*_`").rstrip("*_`")

    # (c) bare keyword — last keyword in the file that isn't part of a template-echo
    for line in reversed(lines):
        if _is_template_echo(line):
            continue
        m = VERDICT_KEYWORD_RE.search(line)
        if m:
            return m.group(1).upper()

    return "(no verdict line found)"


def cmd_synthesize(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    manifest = load_manifest(run_dir)

    out_path = run_dir / args.out
    parts: list[str] = []

    parts.append(f"# Synthesis input — {manifest['run_id']}\n\n")
    parts.append(f"- **Target**: `{manifest['target']}`\n")
    parts.append(f"- **Run dir**: `{run_dir}`\n")
    parts.append(f"- **Created**: {manifest['created']}\n\n")

    parts.append("## Voice roster\n\n")
    parts.append("| Voice | Harness | Status | Elapsed | Finish | Verdict | File |\n")
    parts.append("|---|---|---|---|---|---|---|\n")
    verdicts: dict[str, str] = {}
    for v in manifest["voices"]:
        elapsed = f"{v.get('elapsed_s', 0):.0f}s" if v.get("elapsed_s") is not None else "-"
        finish = v.get("finish_reason") or "-"
        verdict = "-"
        if v["status"] == "complete":
            file_path = run_dir / v["file"]
            if file_path.exists():
                verdict = extract_verdict(file_path.read_text())
                verdicts[v["id"]] = verdict
        elif v["status"] == "error":
            verdict = f"ERROR: {v.get('error_detail', '')[:60]}"
        parts.append(f"| {v['id']} | {v['harness']} | {v['status']} | {elapsed} | {finish} | {verdict} | `{v['file']}` |\n")
    parts.append("\n")

    # Crude verdict-tally (count by direction):
    parts.append("## Verdict tally\n\n")
    tally: dict[str, list[str]] = {}
    for vid, verdict in verdicts.items():
        key = "BREAKS" if "BREAK" in verdict.upper() else \
              "SURVIVES" if "SURVIV" in verdict.upper() else \
              "INDETERMINATE" if "INDETERM" in verdict.upper() else \
              "OTHER"
        tally.setdefault(key, []).append(vid)
    for key, voices in sorted(tally.items()):
        parts.append(f"- **{key}**: {len(voices)} voice(s) — {', '.join(voices)}\n")
    parts.append("\n")

    parts.append("## Per-voice reports (verbatim)\n\n")
    parts.append("---\n\n")
    for v in manifest["voices"]:
        if v["status"] != "complete":
            continue
        file_path = run_dir / v["file"]
        if not file_path.exists():
            continue
        parts.append(f"## Voice: {v['id']} (harness: {v['harness']})\n\n")
        parts.append(file_path.read_text())
        parts.append("\n\n---\n\n")

    out_path.write_text("".join(parts))
    size_kb = out_path.stat().st_size / 1024
    print(f"wrote {out_path} ({size_kb:.1f} KB)")
    print(f"verdict tally: {dict((k, len(v)) for k, v in tally.items())}")
    print()
    print(f"Hand this file to a synthesis voice (typically claude-code) to produce {manifest['synthesis']['file']}.")
    return 0


# -----------------------------------------------------------------------------
# entry
# -----------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Harness-agnostic dispatch manifest for Colosseum adversarial passes.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="Create a new run directory + manifest.")
    pi.add_argument("target", help="Path to the spec/intent doc under review.")
    pi.add_argument("--voices", required=True, help="Comma-separated voice ids.")
    pi.add_argument("--owners", required=True, help="Comma-separated voice:harness mapping.")
    pi.add_argument("--run-dir", default=None, help="Override run dir (default: auto under <project>/.colosseum/attacks/).")
    pi.add_argument("--synthesis-harness", default="claude-code", help="Harness expected to run the synthesis step.")
    pi.set_defaults(func=cmd_init)

    ps = sub.add_parser("status", help="Print manifest state. Exit 0 if all complete, 1 if any pending, 2 if any error.")
    ps.add_argument("run_dir")
    ps.add_argument("--json", action="store_true")
    ps.set_defaults(func=cmd_status)

    pc = sub.add_parser("complete", help="Mark a voice complete.")
    pc.add_argument("run_dir")
    pc.add_argument("--voice", required=True)
    pc.add_argument("--elapsed", type=float, default=None)
    pc.add_argument("--finish-reason", default=None)
    pc.set_defaults(func=cmd_complete)

    pe = sub.add_parser("error", help="Mark a voice errored.")
    pe.add_argument("run_dir")
    pe.add_argument("--voice", required=True)
    pe.add_argument("--detail", required=True)
    pe.add_argument("--elapsed", type=float, default=None)
    pe.set_defaults(func=cmd_error)

    pr = sub.add_parser("reset", help="Flip a voice back to pending.")
    pr.add_argument("run_dir")
    pr.add_argument("--voice", required=True)
    pr.set_defaults(func=cmd_reset)

    pw = sub.add_parser("wait", help="Block until all voices complete or errored.")
    pw.add_argument("run_dir")
    pw.add_argument("--timeout", type=float, default=3600.0)
    pw.add_argument("--poll", type=float, default=10.0)
    pw.set_defaults(func=cmd_wait)

    py = sub.add_parser("synthesize", help="Build the synthesis-prompt input. No LLM calls.")
    py.add_argument("run_dir")
    py.add_argument("--out", default="synthesis-input.md")
    py.set_defaults(func=cmd_synthesize)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
