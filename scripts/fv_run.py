#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
fv-run — harness-agnostic dispatch manifest for multi-model adversarial passes.

The manifest pattern lets multiple harnesses (OMP, OMP, plain shell)
coordinate on a shared adversarial-review run without any in-process coupling.
Each harness reads + updates the same `run.json` file in the run directory;
the manifest IS the state machine — for manifest-mode runs. The in-process
orchestration shape (omp_fanout.py) does not use run.json: there the
dispatcher's own summary.json is the record, and if a manifest exists it is
the invoking orchestrator's job to mark voices complete/error here after
dispatch returns.

USAGE

    # Phase 1: orchestrator (any harness or human) creates the manifest:
    fv_run.py init <target-spec.md> \
        --voices=claude,kimi-k2-6,glm-4-7-flash,gpt-oss-120b \
        --owners=claude:omp,kimi-k2-6:omp,glm-4-7-flash:omp,gpt-oss-120b:omp

    # Phase 2: each harness dispatches its assigned voices, writes the per-voice file,
    # and marks the manifest entry complete (or errored):
    fv_run.py complete <run-dir> --voice=claude --elapsed=339 --finish-reason=stop
    fv_run.py error    <run-dir> --voice=kimi-k2-6 --detail="HTTP 408 at 240s" --elapsed=239

    # Inspection:
    fv_run.py status <run-dir>          # human-readable table
    fv_run.py status <run-dir> --json   # machine-readable manifest

    # Re-run a voice (flips status back to pending):
    fv_run.py reset <run-dir> --voice=kimi-k2-6

    # Build the synthesis prompt body (deterministic, no LLM call). Concatenates
    # per-voice files into one document with a structural-overlap header:
    fv_run.py synthesize <run-dir> --out=synthesis-input.md

    # Wait for all voices to land (blocking, no LLM call). Exits 0 when all
    # voices are terminal AND at least one completed; 1 on timeout; 2 when
    # all voices are terminal but none completed (zero evidence — G2
    # INCOMPLETE). Useful inside a `make` rule or shell pipeline:
    fv_run.py wait <run-dir> --timeout=3600

MANIFEST SCHEMA

    {
      "run_id":  "<basename>-<ISO-UTC-timestamp>",
      "target":  "<path/to/spec-under-review>",
      "created": "<ISO-UTC-timestamp>",
      "voices": [
        {
          "id":            "<voice-id>",            // unique within the run
          "harness":       "<omp|omp|shell|...>",
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
        "harness": "omp",
        "status":  "pending"
      }
    }
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sys
import tempfile
import time
from contextlib import contextmanager
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
        manifest = json.load(f)
    # G2: a zero-voice manifest is an invalid run, not a trivially-complete one.
    if not manifest.get("voices"):
        sys.exit(f"error: manifest {p} has zero voices — invalid run")
    ids = [v["id"] for v in manifest["voices"]]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        sys.exit(f"error: manifest {p} has duplicate voice ids: {dupes}")
    return manifest


def save_manifest(run_dir: Path, manifest: dict[str, Any]) -> None:
    # Unique temp file per writer (a shared fixed .tmp name crashes
    # concurrent writers) → atomic rename so readers never observe a
    # half-written manifest.
    p = manifest_path(run_dir)
    fd, tmp_name = tempfile.mkstemp(dir=run_dir, prefix="run.json.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(manifest, f, indent=2)
            f.write("\n")
        os.replace(tmp_name, p)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


@contextmanager
def manifest_lock(run_dir: Path):
    """Exclusive advisory lock serializing read-modify-write cycles.
    Atomic rename alone protects readers, not concurrent writers: two
    unlocked `complete` calls interleave load/save and one update is lost
    (reproduced 4-7 losses per 24 writers before this lock)."""
    lock_path = run_dir / "run.json.lock"
    with lock_path.open("w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _parse_run_ts(ts: str) -> float:
    return datetime.strptime(ts, "%Y-%m-%dT%H%M%SZ").replace(
        tzinfo=timezone.utc).timestamp()


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
    prefix = harness if harness in {"omp", "omp"} else harness
    if voice_id == "claude" and harness == "omp":
        return "claude.md"
    return f"{prefix}-{safe}.md"


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.target).resolve()
    if not target.exists():
        sys.exit(f"error: target {target} does not exist")

    voice_ids = [v.strip() for v in args.voices.split(",") if v.strip()]
    if not voice_ids:
        sys.exit("error: --voices is empty — a zero-voice run is invalid")
    if len(voice_ids) != len(set(voice_ids)):
        dupes = sorted({v for v in voice_ids if voice_ids.count(v) > 1})
        sys.exit(f"error: duplicate voice ids in --voices: {dupes}")
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
        # Default: <target's project>/.fv/attacks/<run-id>/
        # Walk up from target looking for .fv, fall back to target parent.
        parent = target.parent
        while parent != parent.parent:
            if (parent / ".fv").is_dir():
                break
            parent = parent.parent
        if (parent / ".fv").is_dir():
            run_dir = parent / ".fv" / "attacks" / run_id
        else:
            run_dir = target.parent / f"attacks-{run_id}"

    run_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "run_id":  run_id,
        "target":  str(target),
        "created": now,
        "phase":   args.phase,
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
        print(f"phase:  {manifest.get('phase', 'attack')}")
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
    with manifest_lock(run_dir):
        manifest = load_manifest(run_dir)
        voice = find_voice(manifest, args.voice)

        file_path = run_dir / voice["file"]
        if not file_path.exists():
            sys.exit(f"error: voice file {file_path} does not exist; write it before marking complete")
        # Freshness + non-emptiness: an empty or leftover file from before
        # this run (or before this voice's last reset) is not evidence.
        if file_path.stat().st_size == 0:
            sys.exit(f"error: voice file {file_path} is empty; refusing to mark complete")
        floor_ts = _parse_run_ts(manifest["created"])
        for attempt in voice.get("history", []):
            if "reset_at" in attempt:
                floor_ts = max(floor_ts, _parse_run_ts(attempt["reset_at"]))
        if file_path.stat().st_mtime < floor_ts - 1.0:
            sys.exit(f"error: voice file {file_path} predates this run/attempt "
                     f"(stale output); rewrite it before marking complete")

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
    with manifest_lock(run_dir):
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
    with manifest_lock(run_dir):
        manifest = load_manifest(run_dir)
        voice = find_voice(manifest, args.voice)

        # Retain the retry history: the prior attempt's outcome stays in the
        # record instead of being silently erased.
        attempt = {k: voice[k] for k in ("status", "elapsed_s", "finish_reason", "error_detail")
                   if k in voice}
        attempt["reset_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        voice.setdefault("history", []).append(attempt)

        # Move any stale output aside so the next attempt cannot silently
        # claim the previous attempt's file.
        file_path = run_dir / voice["file"]
        if file_path.exists():
            aside = run_dir / f"{voice['file']}.attempt{len(voice['history'])}"
            file_path.rename(aside)
            attempt["output_moved_to"] = aside.name

        voice["status"] = "pending"
        voice.pop("elapsed_s", None)
        voice.pop("finish_reason", None)
        voice.pop("error_detail", None)
        save_manifest(run_dir, manifest)
    print(f"reset {args.voice} to pending (attempt {len(voice['history'])} retained in history)")
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
            # G2: all-terminal is not success. A run in which no voice
            # completed produced zero evidence — exit nonzero (INCOMPLETE).
            if counts["complete"] == 0:
                print(f"done but INCOMPLETE — zero completed voices: {counts}")
                return 2
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

    # G2: synthesis over pending/errored inputs is partial evidence. Refuse
    # unless explicitly overridden, and label the output when overridden.
    not_complete = [v for v in manifest["voices"] if v["status"] != "complete"]
    if not_complete and not args.allow_partial:
        detail = ", ".join(f"{v['id']}={v['status']}" for v in not_complete)
        sys.exit(f"error: {len(not_complete)} voice(s) not complete ({detail}); "
                 f"re-run them, or pass --allow-partial to synthesize anyway "
                 f"(the output will be labeled PARTIAL)")
    complete_count = sum(1 for v in manifest["voices"] if v["status"] == "complete")
    if complete_count == 0:
        sys.exit("error: zero completed voices — nothing to synthesize, "
                 "and --allow-partial cannot conjure evidence")

    out_path = run_dir / args.out
    parts: list[str] = []

    parts.append(f"# Synthesis input — {manifest['run_id']}\n\n")
    if not_complete:
        detail = ", ".join(f"{v['id']} ({v['status']})" for v in not_complete)
        parts.append(f"> **PARTIAL SYNTHESIS INPUT** — {len(not_complete)} voice(s) "
                     f"did not complete: {detail}. Their absence is a coverage gap, "
                     f"not agreement.\n\n")
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
    print(f"Hand this file to a synthesis voice (typically omp) to produce {manifest['synthesis']['file']}.")
    return 0


# -----------------------------------------------------------------------------
# entry
# -----------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Harness-agnostic dispatch manifest for FV adversarial passes.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="Create a new run directory + manifest.")
    pi.add_argument("target", help="Path to the spec/intent doc under review.")
    pi.add_argument("--voices", required=True, help="Comma-separated voice ids.")
    pi.add_argument("--owners", required=True, help="Comma-separated voice:harness mapping.")
    pi.add_argument("--run-dir", default=None, help="Override run dir (default: auto under <project>/.fv/attacks/).")
    pi.add_argument("--synthesis-harness", default="omp", help="Harness expected to run the synthesis step.")
    pi.add_argument("--phase", default="attack",
                    choices=["attack", "critique", "defense", "re-critique"],
                    help="Which round of the loop this run is (recorded in run.json).")
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

    py = sub.add_parser("synthesize", help="Build the synthesis-prompt input. No LLM calls. Refuses pending/errored voices unless --allow-partial.")
    py.add_argument("run_dir")
    py.add_argument("--out", default="synthesis-input.md")
    py.add_argument("--allow-partial", action="store_true",
                    help="synthesize despite pending/errored voices; output is labeled PARTIAL")
    py.set_defaults(func=cmd_synthesize)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
