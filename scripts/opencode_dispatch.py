#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
OpenCode per-section adversarial dispatch — canonical Colosseum orchestrator.

This script is project-agnostic. Each project supplies a JSON config naming
the target spec, the voice roster, and the slice plan. The script invokes
`opencode run --agent spec-adversary --model <voice> ...` once per
(voice, slice) pair, captures stdout, runs a truncation-detection pass,
retries on failure, and aggregates per-voice files plus a summary.

This is the Mode 1 dispatch path described in
`colosseum/skills/colosseum-adversarial/SKILL.md`. The
`external-model-mcp` MCP tools (`query_gateway`, `query_openai`,
`query_google`, `fan_out_query`) are Mode 3 fallbacks, NOT this script's
purpose. Reach for the MCP tools only when OpenCode is not installed.

USAGE
    # Copy this script to <project>/.colosseum/scripts/opencode_dispatch.py
    # and supply a config at <project>/.colosseum/dispatch.json
    # (see colosseum/scripts/dispatch.config.example.json for the schema).

    uv run --script opencode_dispatch.py \\
        --config <project>/.colosseum/dispatch.json \\
        [--voices=A,B,C] [--slices=X,Y] [--sequential]

    --voices and --slices accept comma-separated subsets for retry / debug.
    --sequential runs voices one at a time (default: voices in parallel,
    slices sequential within each voice).

CONFIG SCHEMA
    See colosseum/scripts/dispatch.config.example.json. Required fields:
      project_root       - absolute path to the project being attacked
      target_spec        - absolute path to the spec/intent doc
      run_tag_prefix     - filesystem-safe prefix for the output dir
      voices[]           - list of {id, model, note?}
      slices[]           - list of {name, label, headers[], attack_emphasis}
      context_appendix?  - optional shared-context block for all calls
      per_call_timeout?  - seconds, default 1800
      max_retries?       - default 2
      output_caps?       - optional {limit_output: N} reminder note

OUTPUT
    <project_root>/.colosseum/attacks/<run-tag>/
    ├── per-section/
    │   └── <voice-id-slug>/
    │       └── <slice-name>.md      # one per (voice, slice)
    ├── opencode-<voice-id-slug>.md  # aggregated per-voice
    ├── dispatch.log
    └── summary.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────
# Config loading
# ─────────────────────────────────────────────────────────────────────────


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        sys.exit(f"FATAL: config not found at {config_path}")
    cfg = json.loads(config_path.read_text())
    for required in ("project_root", "target_spec", "run_tag_prefix", "voices", "slices"):
        if required not in cfg:
            sys.exit(f"FATAL: config missing required field '{required}'")
    cfg["project_root"] = Path(cfg["project_root"]).resolve()
    cfg["target_spec"] = Path(cfg["target_spec"]).resolve()
    cfg.setdefault("context_appendix", "")
    cfg.setdefault("per_call_timeout", 1800)
    cfg.setdefault("max_retries", 2)
    return cfg


# ─────────────────────────────────────────────────────────────────────────
# Message construction
# ─────────────────────────────────────────────────────────────────────────


def build_message(voice_id: str, slice_spec: dict, target_spec: Path, context_appendix: str) -> str:
    headers_block = "\n".join(f"  - {h}" for h in slice_spec["headers"])
    appendix_block = f"\n\n{context_appendix}\n" if context_appendix.strip() else ""
    return f"""VOICE_ID: {voice_id}  (use this string as <voice-id> in your output header)

TARGET_SPEC: {target_spec}

TARGET_SLICE: {slice_spec['name']} — {slice_spec['label']}

Read these headers from TARGET_SPEC (use the Read tool):
{headers_block}

Attack only what is INSIDE these header ranges. Do not attack content
outside them.

Attack-category emphasis for this slice:
{slice_spec['attack_emphasis']}{appendix_block}

Begin by reading TARGET_SPEC at the named header ranges, then produce
your attack report per the Output structure in your system prompt."""


# ─────────────────────────────────────────────────────────────────────────
# Truncation detection
# ─────────────────────────────────────────────────────────────────────────

_REPORT_MARKERS = ("## Attacks", "## Slice-local summary", "VERDICT", "### 1.")
_MIN_REPORT_CHARS = 500


def _is_truncated_stub(content: str) -> bool:
    """Detect mid-ReAct truncation. OpenCode exits cleanly when a model emits
    its "I'll read the file..." preamble and then fails to continue past the
    first tool_use. A real report contains structural markers and is large
    enough to plausibly hold one."""
    if len(content) < _MIN_REPORT_CHARS:
        return True
    return not any(m in content for m in _REPORT_MARKERS)


# ─────────────────────────────────────────────────────────────────────────
# Dispatch primitives
# ─────────────────────────────────────────────────────────────────────────

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


async def dispatch_one(
    voice_id: str,
    model_id: str,
    variant: str | None,
    slice_spec: dict,
    cfg: dict,
    outdir: Path,
) -> dict:
    out_dir = outdir / "per-section" / voice_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slice_spec['name']}.md"

    message = build_message(voice_id, slice_spec, cfg["target_spec"], cfg["context_appendix"])
    cmd = [
        "opencode", "run",
        "--agent", "spec-adversary",
        "--model", model_id,
        "--format", "default",
        "--dangerously-skip-permissions",
    ]
    if variant:
        cmd.extend(["--variant", variant])
    cmd.append(message)
    t0 = datetime.now(timezone.utc)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cfg["project_root"]),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=cfg["per_call_timeout"]
            )
        except asyncio.TimeoutError:
            proc.kill()
            elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
            return {
                "voice": voice_id, "slice": slice_spec["name"],
                "error": f"timeout after {cfg['per_call_timeout']}s",
                "elapsed_s": elapsed,
            }

        elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
        content = _ANSI_RE.sub("", stdout.decode("utf-8", errors="replace"))
        lines = content.splitlines()
        if lines and lines[0].startswith("> "):
            lines = lines[1:]
            while lines and not lines[0].strip():
                lines = lines[1:]
        content = "\n".join(lines).strip()

        if proc.returncode != 0 or not content:
            err = stderr.decode("utf-8", errors="replace")[:1000]
            return {
                "voice": voice_id, "slice": slice_spec["name"],
                "error": f"exit={proc.returncode}: {err}",
                "elapsed_s": elapsed,
            }

        if _is_truncated_stub(content):
            return {
                "voice": voice_id, "slice": slice_spec["name"],
                "error": f"truncated stub (exit=0, {len(content)} chars, no structural markers)",
                "elapsed_s": elapsed,
                "stub_content_preview": content[:200],
            }

        out_path.write_text(content)
        return {
            "voice": voice_id, "slice": slice_spec["name"],
            "out_path": str(out_path),
            "elapsed_s": elapsed,
            "chars": len(content),
        }
    except Exception as e:
        elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
        return {
            "voice": voice_id, "slice": slice_spec["name"],
            "error": f"{type(e).__name__}: {e}",
            "elapsed_s": elapsed,
        }


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%SZ")


def _log_both(msg: str, logf) -> None:
    line = f"{_ts()} {msg}"
    print(line, flush=True)
    logf.write(line + "\n")
    logf.flush()


async def dispatch_voice(
    voice_id: str,
    model_id: str,
    variant: str | None,
    slices: list[dict],
    cfg: dict,
    outdir: Path,
    log_path: Path,
) -> list[dict]:
    results = []
    log_path.parent.mkdir(parents=True, exist_ok=True)
    total = len(slices)
    voice_t0 = datetime.now(timezone.utc)
    with log_path.open("a") as logf:
        variant_label = f" [variant={variant}]" if variant else ""
        _log_both(f"→ voice {voice_id}{variant_label}: starting {total}-slice dispatch", logf)
        for idx, slice_spec in enumerate(slices, start=1):
            slice_name = slice_spec["name"]
            _log_both(f"  ⇢ [{idx}/{total}] {voice_id}/{slice_name} dispatching...", logf)
            for attempt in range(cfg["max_retries"] + 1):
                r = await dispatch_one(voice_id, model_id, variant, slice_spec, cfg, outdir)
                if "error" not in r:
                    if attempt > 0:
                        _log_both(f"    ↻ {voice_id}/{slice_name} succeeded on attempt {attempt + 1}", logf)
                    break
                _log_both(f"    ⚠ {voice_id}/{slice_name} attempt {attempt + 1} failed ({r['elapsed_s']:.0f}s): {r['error'][:120]}", logf)
            results.append(r)
            if "error" in r:
                _log_both(f"  ✗ [{idx}/{total}] {voice_id}/{slice_name} ABANDONED after {cfg['max_retries'] + 1} attempts", logf)
            else:
                _log_both(f"  ✓ [{idx}/{total}] {voice_id}/{slice_name} OK ({r['elapsed_s']:.0f}s, {r['chars']:,} chars)", logf)
        voice_elapsed = (datetime.now(timezone.utc) - voice_t0).total_seconds()
        n_ok = sum(1 for r in results if "error" not in r)
        _log_both(f"─ voice {voice_id} done: {n_ok}/{total} slices OK in {voice_elapsed:.0f}s", logf)
    return results


def aggregate_voice(voice_id: str, slices: list[dict], results: list[dict], outdir: Path, target_spec: Path) -> Path:
    agg_path = outdir / f"opencode-{voice_id}.md"
    header = f"# {voice_id} — {target_spec.name} adversarial pass (OpenCode subagent dispatch, per-section)\n\n"
    header += f"- **Target**: {target_spec}\n"
    header += f"- **Slices dispatched**: {len(slices)}\n\n"
    parts = [header]
    for slice_spec, r in zip(slices, results):
        parts.append(f"---\n\n## Slice: {slice_spec['name']}\n\n")
        if "error" in r:
            parts.append(f"**ERROR** ({r['elapsed_s']:.1f}s): {r['error'][:500]}\n")
        else:
            parts.append(f"*Elapsed: {r['elapsed_s']:.1f}s, {r['chars']:,} chars.*\n\n")
            parts.append(Path(r["out_path"]).read_text())
            parts.append("\n")
    agg_path.write_text("".join(parts))
    return agg_path


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="path to dispatch.json")
    ap.add_argument("--voices", default=None, help="comma-separated voice id slugs to dispatch (default: all)")
    ap.add_argument("--slices", default=None, help="comma-separated slice names to dispatch (default: all)")
    ap.add_argument("--sequential", action="store_true", help="run voices sequentially (default: parallel)")
    args = ap.parse_args()

    cfg = load_config(Path(args.config).resolve())

    run_tag_env = os.environ.get("COLOSSEUM_RUN_TAG")
    if run_tag_env:
        run_tag = run_tag_env
    else:
        _ts_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        run_tag = f"{cfg['run_tag_prefix']}-{_ts_iso}"
    outdir = cfg["project_root"] / ".colosseum" / "attacks" / run_tag
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "per-section").mkdir(exist_ok=True)

    default_variant = cfg.get("default_variant", "max")
    voices_cfg = [
        (v["id"], v["model"], v.get("variant", default_variant), v.get("note", ""))
        for v in cfg["voices"]
    ]
    if args.voices:
        wanted = set(args.voices.split(","))
        voices_cfg = [v for v in voices_cfg if v[0] in wanted]

    slices_cfg = cfg["slices"]
    if args.slices:
        wanted = set(args.slices.split(","))
        slices_cfg = [s for s in slices_cfg if s["name"] in wanted]

    log_path = outdir / "dispatch.log"
    with log_path.open("a") as logf:
        logf.write(f"\n=== Subagent dispatch starting {datetime.now(timezone.utc).isoformat()} ===\n")
        logf.write(f"Config: {args.config}\n")
        logf.write(f"Voices: {[v[0] for v in voices_cfg]}\n")
        logf.write(f"Slices: {[s['name'] for s in slices_cfg]}\n")
        logf.write(f"Output: {outdir}\n\n")

    print(f"Output dir: {outdir}")
    print(f"Voices ({len(voices_cfg)}): {[v[0] for v in voices_cfg]}")
    print(f"Slices ({len(slices_cfg)}): {[s['name'] for s in slices_cfg]}")
    print(f"Total calls: {len(voices_cfg) * len(slices_cfg)}")

    if args.sequential:
        all_results = {}
        for voice_id, model_id, variant, _note in voices_cfg:
            print(f"\n→ Dispatching voice {voice_id} (variant={variant}) sequentially...")
            results = await dispatch_voice(voice_id, model_id, variant, slices_cfg, cfg, outdir, log_path)
            all_results[voice_id] = results
    else:
        print("\nDispatching all voices in parallel...")
        tasks = [
            dispatch_voice(voice_id, model_id, variant, slices_cfg, cfg, outdir, log_path)
            for voice_id, model_id, variant, _note in voices_cfg
        ]
        results_list = await asyncio.gather(*tasks, return_exceptions=False)
        all_results = {v[0]: r for v, r in zip(voices_cfg, results_list)}

    print("\n=== Aggregating per-voice files ===")
    summary = []
    for voice_id, model_id, variant, _note in voices_cfg:
        results = all_results[voice_id]
        agg_path = aggregate_voice(voice_id, slices_cfg, results, outdir, cfg["target_spec"])
        n_ok = sum(1 for r in results if "error" not in r)
        total_elapsed = sum(r["elapsed_s"] for r in results)
        total_chars = sum(r.get("chars", 0) for r in results if "error" not in r)
        summary.append({
            "voice": voice_id,
            "model": model_id,
            "variant": variant,
            "slices_ok": n_ok,
            "slices_total": len(results),
            "total_elapsed_s": total_elapsed,
            "total_chars": total_chars,
        })
        print(f"  {voice_id}: {n_ok}/{len(results)} slices OK, {total_elapsed:.0f}s total, {total_chars:,} chars → {agg_path.name}")

    (outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nSummary written to {outdir}/summary.json")


if __name__ == "__main__":
    asyncio.run(main())
