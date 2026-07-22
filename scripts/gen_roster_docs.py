#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
gen_roster_docs — regenerate the voice-roster blocks in the hand-maintained
sites from the authoritative registry at registry/voices.json (C4).

The registry, not the prose docs, is the source of truth for the adversarial
voice roster. This tool writes the enumerable roster content into each site
between explicit markers, leaving the surrounding prose untouched:

  markdown sites   content between
                     <!-- BEGIN GENERATED: voice-roster ... -->
                     <!-- END GENERATED: voice-roster -->
                   is replaced. The markers must already exist in the file
                   (a first-time conversion adds them by hand); a missing
                   marker pair is an error, never a silent skip.

  dispatch.config.example.json   the OpenCode `voices` array, OMP-native
                   routes, and roster comments are regenerated from the
                   registry; every other key is preserved.
                   The file is re-serialized deterministically so `--check` is stable.

It also maintains the derived `content_hash` on each registry profile
(recomputed from the profile's voice id+variant set), updating it in place
without reformatting the rest of registry/voices.json.

USAGE
    gen_roster_docs.py [--repo <path>]        # write (default)
    gen_roster_docs.py --check [--repo <path>] # exit nonzero on any drift

Exit 0 clean, 1 drift (under --check) or a write error, 2 usage/registry error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO / "registry" / "voices.json"

BEGIN_CANONICAL = ("<!-- BEGIN GENERATED: voice-roster (source: registry/voices.json "
                   "via scripts/gen_roster_docs.py — do not edit by hand) -->")
END_CANONICAL = "<!-- END GENERATED: voice-roster -->"
BEGIN_RE = re.compile(r"^\s*<!--\s*BEGIN GENERATED: voice-roster\b.*?-->\s*$")
END_RE = re.compile(r"^\s*<!--\s*END GENERATED: voice-roster\s*-->\s*$")


# ─────────────────────────────────────────────────────────────────────────
# Registry access + profile hashing (imported by doctor and tests/r0)
# ─────────────────────────────────────────────────────────────────────────


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    if not path.exists():
        sys.exit(f"FATAL: registry not found at {path}")
    return json.loads(path.read_text())


def voice_by_id(reg: dict, vid: str) -> dict:
    for v in reg["voices"]:
        if v["id"] == vid:
            return v
    sys.exit(f"FATAL: profile references unknown voice id {vid!r}")


def profile_content_hash(profile: dict) -> str:
    """Content address a run profile over its normalized voice id+variant set.
    The label is deliberately NOT hashed: a pin `canonical-4@<hash>` binds the
    membership, so renaming the profile keeps the hash while adding/removing a
    voice or changing a variant moves it."""
    normalized = {
        "voices": sorted(
            ({"id": v["id"], "variant": v.get("variant", "max")} for v in profile["voices"]),
            key=lambda d: d["id"],
        )
    }
    blob = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def omp_route_hash(route: dict) -> str:
    """Content-address the exact OMP agent, thinking level, and model routes."""
    normalized = {
        "agent": route["agent"],
        "thinking_level": route["thinking_level"],
        "voices": sorted(
            ({"id": v["id"], "model": v["model"]} for v in route["voices"]),
            key=lambda d: d["id"],
        ),
    }
    blob = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def profile_by_name(reg: dict, name: str) -> dict:
    for p in reg["profiles"]:
        if p["name"] == name:
            return p
    sys.exit(f"FATAL: no profile named {name!r}")


# ─────────────────────────────────────────────────────────────────────────
# Rendering helpers
# ─────────────────────────────────────────────────────────────────────────

_SEAT = {
    "burnt": "Burnt gateway",
    "openai": "direct openai provider",
    "google": "direct google provider",
    "fireworks-ai": "Fireworks",
    "ds4": "local ds4 runner",
    "lmstudio": "local LM Studio",
    None: "in-harness Agent subagent",
}


def _status_label(v: dict) -> str:
    status = v["status"]
    cal = v["calibration"]
    if status == "canonical-panel":
        return "**canonical-panel** (calibrated)"
    if status == "candidate":
        if cal == "pending":
            return "candidate (calibration pending)"
        if cal.startswith("partial"):
            return "candidate (partial calibration)"
        return "candidate"
    if status == "local-specialist":
        return "local-specialist"
    return "excluded"


def _caveat(v: dict) -> str:
    bits = []
    for env in v.get("requires_env", []):
        bits.append(f"requires `{env}`")
    if v.get("endpoint"):
        bits.append(f"endpoint `{v['endpoint']}`")
    return (" — " + "; ".join(bits) + ".") if bits else ""


def dispatchable_opencode_voices(reg: dict) -> list[dict]:
    """OpenCode voices a runner may dispatch: canonical-panel + candidate, in
    registry order. Excludes in-harness claude-agent, local specialists, and
    excluded voices."""
    return [v for v in reg["voices"]
            if v["harness"] == "opencode" and v["status"] in ("canonical-panel", "candidate")]


# ─────────────────────────────────────────────────────────────────────────
# Per-site markdown renderers
# ─────────────────────────────────────────────────────────────────────────


def render_adversarial_model_ids(reg: dict) -> str:
    """skills/colosseum-adversarial/SKILL.md — 'Per-voice voice IDs to pass to
    --model' list."""
    lines = []
    for v in dispatchable_opencode_voices(reg):
        seat = _SEAT[v["provider"]]
        lines.append(f"- `{v['model']}` — {v['family']}, {seat}. {_status_label(v)}{_caveat(v)}")
    # Local specialists get a substitution note; the wildcard covers any other
    # LM Studio model a user has loaded.
    for v in reg["voices"]:
        if v["status"] == "local-specialist":
            lines.append(f"- `{v['model']}` — {v['family']}, local. local-specialist "
                         f"(Lean-only; substitute for one general voice only when the spec IS a "
                         f"Lean theorem).")
    lines.append("- `lmstudio/<local-model-id>` — any model configured under OpenCode's "
                 "`lmstudio` provider (matches names in your `lms ls`).")
    excluded = [v["id"] for v in reg["voices"] if v["status"] == "excluded"]
    if excluded:
        lines.append(f"- **Excluded** (do NOT dispatch): {', '.join('`'+e+'`' for e in excluded)} "
                     f"— see `registry/voices.json` for the calibration evidence behind each "
                     f"exclusion.")
    return "\n".join(lines)


def render_code_adversarial_frontier(reg: dict) -> str:
    """skills/colosseum-code-adversarial/SKILL.md — the pinned frontier IDs, as
    one line (lives inside a bulleted list item)."""
    prof = profile_by_name(reg, "canonical-4")
    parts = []
    for pv in prof["voices"]:
        v = voice_by_id(reg, pv["id"])
        if v["harness"] != "opencode":
            continue  # claude-agent is the in-harness voice, not an OpenCode target
        status = "canonical-panel" if v["status"] == "canonical-panel" else "candidate"
        parts.append(f"`{v['model']}` ({v['family']}, {status})")
    return ", ".join(parts)


def render_scripts_readme_roster(reg: dict) -> str:
    """scripts/README.md — full reference table."""
    rows = [
        "| Voice id | Reference model | OMP model | Family | Reference harness | Status | Reference calibration | OMP calibration |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for v in reg["voices"]:
        cal = "pending" if v["calibration"] == "pending" else (
            "n/a" if v["calibration"].startswith("n/a") else "cited")
        omp_model = f"`{v['omp_model']}`" if v.get("omp_model") else "n/a"
        omp_cal = v.get("omp_calibration", "n/a")
        rows.append(
            f"| `{v['id']}` | `{v['model']}` | {omp_model} | {v['family']} | "
            f"{v['harness']} | {v['status']} | {cal} | {omp_cal} |")
    rows.append("")
    rows.append(
        "Reference calibration applies only to the recorded OpenCode or Claude Code "
        "route. OMP calibration is tracked separately; `pending` native routes are "
        "experimental and cannot inherit the reference claim.")
    return "\n".join(rows)


def render_install_roster(reg: dict) -> str:
    """INSTALL.md §7.2 — canonical panel reference (model strings + auth)."""
    prof = profile_by_name(reg, "canonical-4")
    lines = [f"**Canonical panel (`{prof['name']}@{prof['content_hash']}`).** The milestone "
             "membership has calibrated OpenCode/Claude Code routes and separately tracked "
             "OMP-native routes:", ""]
    for pv in prof["voices"]:
        v = voice_by_id(reg, pv["id"])
        if v["harness"] != "opencode":
            lines.append(f"- `{v['id']}` — calibrated in-harness Claude Code Agent route; "
                         f"OMP `{v['omp_model']}` is separately {v['omp_calibration']}.")
            continue
        env = f" Set {', '.join('`'+e+'`' for e in v['requires_env'])}." if v["requires_env"] else ""
        ep = f" Local endpoint `{v['endpoint']}` must be reachable." if v.get("endpoint") else ""
        lines.append(f"- `{v['model']}` — {v['family']}, {_SEAT[v['provider']]}. "
                     f"{_status_label(v)}.{env}{ep}")
    lines.append("")
    lines.append("OMP-native model patterns and route calibration are generated into "
                 "`.colosseum/dispatch.json`. Confirm each pattern in OMP's `/model` picker "
                 "before a run. OpenCode pins should still be probed with "
                 "`opencode run --model <id> \"Reply with exactly: ok\"`.")
    return "\n".join(lines)


MD_SITES = {
    "skills/colosseum-adversarial/SKILL.md": render_adversarial_model_ids,
    "skills/colosseum-code-adversarial/SKILL.md": render_code_adversarial_frontier,
    "scripts/README.md": render_scripts_readme_roster,
    "INSTALL.md": render_install_roster,
}


# ─────────────────────────────────────────────────────────────────────────
# dispatch.config.example.json renderers
# ─────────────────────────────────────────────────────────────────────────

DISPATCH_CONFIG = "scripts/dispatch.config.example.json"


def render_dispatch_voices(reg: dict) -> list[dict]:
    """The canonical-4 profile's OpenCode voices as dispatch-config entries.
    claude-agent is dropped: it never runs through opencode_dispatch.py."""
    prof = profile_by_name(reg, "canonical-4")
    out = []
    for pv in prof["voices"]:
        v = voice_by_id(reg, pv["id"])
        if v["harness"] != "opencode":
            continue
        note = f"{v['family']} via {_SEAT[v['provider']]}. status={v['status']}. {v['notes']}"
        out.append({"id": v["id"], "model": v["model"], "note": note})
    return out


def render_omp_native_config(reg: dict) -> dict:
    """Exact OMP ModelRegistry routes for the canonical profile.

    OMP route calibration is deliberately independent from the voice's
    OpenCode/Claude Code calibration.
    """
    prof = profile_by_name(reg, "canonical-4")
    voices = []
    for pv in prof["voices"]:
        voice = voice_by_id(reg, pv["id"])
        model = voice.get("omp_model")
        calibration = voice.get("omp_calibration")
        if not model or not calibration:
            sys.exit(f"FATAL: canonical voice {voice['id']!r} has no complete OMP route")
        voices.append({
            "id": voice["id"],
            "model": model,
            "family": voice["family"],
            "calibration": calibration,
        })
    route = {
        "profile": f"{prof['name']}@{prof['content_hash']}",
        "agent": "colosseum-spec-adversary",
        "thinking_level": "max",
        "calibration": ("pending" if any(v["calibration"] == "pending" for v in voices)
                        else "cited"),
        "voices": voices,
    }
    route["route_hash"] = omp_route_hash(route)
    return route


def render_dispatch_excluded_comment(reg: dict) -> str:
    excluded = [v for v in reg["voices"] if v["status"] == "excluded"]
    specialists = [v for v in reg["voices"] if v["status"] == "local-specialist"]
    parts = ["Voices known to fail adversarial spec review (see registry/voices.json for "
             "calibration evidence):"]
    for v in excluded:
        reason = v["calibration"].split(":", 1)[-1].strip() if ":" in v["calibration"] else v["calibration"]
        parts.append(f" {v['id']} — {reason}")
    for v in specialists:
        parts.append(f" {v['id']} belongs in Lean-specific verification work, not general "
                     f"adversarial spec review — substitute only when the spec is a Lean theorem.")
    return "".join(parts)


# ─────────────────────────────────────────────────────────────────────────
# Marker replacement
# ─────────────────────────────────────────────────────────────────────────


def replace_marked_block(text: str, rendered: str, site: str) -> str:
    lines = text.splitlines()
    begin_idx = end_idx = None
    for i, line in enumerate(lines):
        if begin_idx is None and BEGIN_RE.match(line):
            begin_idx = i
        elif begin_idx is not None and END_RE.match(line):
            end_idx = i
            break
    if begin_idx is None or end_idx is None:
        sys.exit(f"FATAL: {site} is missing the voice-roster BEGIN/END markers. "
                 f"Add them by hand around the roster content, then re-run.")
    new_lines = (lines[:begin_idx]
                 + [BEGIN_CANONICAL, rendered, END_CANONICAL]
                 + lines[end_idx + 1:])
    trailing_nl = "\n" if text.endswith("\n") else ""
    return "\n".join(new_lines) + trailing_nl


def render_dispatch_config(reg: dict, current_text: str) -> str:
    cfg = json.loads(current_text)
    prof = profile_by_name(reg, "canonical-4")
    cfg["_comment_top"] = (
        "Shared adversarial dispatch config. opencode_dispatch.py reads the OpenCode "
        "voices and slice plan; OMP-native fan-out reads omp_native.")
    cfg["_comment_canonical_panel"] = (
        f"Canonical membership {prof['name']}@{prof['content_hash']}. Existing fitness "
        "evidence is transport-specific; see registry/voices.json.")
    cfg["voices"] = render_dispatch_voices(reg)
    cfg["_comment_claude_voice"] = (
        "claude-agent runs through the calibrated Claude Code Agent route or the "
        "separately tracked OMP-native route. It never runs through opencode_dispatch.py.")
    cfg["_comment_excluded_voices"] = render_dispatch_excluded_comment(reg)
    cfg["omp_native"] = render_omp_native_config(reg)
    cfg["_comment_omp_native"] = (
        "Generated from registry/voices.json. Run from OMP with the "
        "colosseum-adversarial skill's omp_fanout.py helper. A pending calibration "
        "must be reported as uncalibrated; never borrow OpenCode fitness evidence.")
    return json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"


# ─────────────────────────────────────────────────────────────────────────
# Profile content_hash maintenance in the registry (targeted, no reformat)
# ─────────────────────────────────────────────────────────────────────────

_HASH_RE = re.compile(r'("content_hash"\s*:\s*")sha256:[0-9a-f]+(")')


def sync_registry_hashes(reg: dict, registry_text: str) -> tuple[str, list[str]]:
    """Return (new_text, drifts). Replaces each profile's embedded content_hash
    with the recomputed value, in profile order, without touching other bytes."""
    wanted = [profile_content_hash(p) for p in reg["profiles"]]
    drifts: list[str] = []
    it = iter(wanted)

    def _sub(m: re.Match) -> str:
        h = next(it)
        return f"{m.group(1)}{h}{m.group(2)}"

    # First detect drift for reporting, then rewrite.
    found = _HASH_RE.findall(registry_text)
    for prof, want in zip(reg["profiles"], wanted):
        if prof.get("content_hash") != want:
            drifts.append(f"profile {prof['name']}: stored {prof.get('content_hash')} != {want}")
    if len(found) != len(wanted):
        drifts.append(f"registry has {len(found)} content_hash field(s), {len(wanted)} profile(s)")
    new_text = _HASH_RE.sub(_sub, registry_text)
    return new_text, drifts


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=REPO)
    ap.add_argument("--check", action="store_true",
                    help="exit nonzero on drift instead of writing")
    args = ap.parse_args()
    repo = args.repo.resolve()
    reg = load_registry(repo / "registry" / "voices.json")

    drift: list[str] = []
    wrote: list[str] = []

    # Canonicalize in-memory profile hashes first so every renderer (e.g. the
    # INSTALL panel line) emits the recomputed value, not the stored one.
    for prof in reg["profiles"]:
        prof["content_hash"] = profile_content_hash(prof)

    # Registry profile hashes (rewrite the stored value in place on drift).
    reg_path = repo / "registry" / "voices.json"
    reg_text = reg_path.read_text()
    new_reg_text, hash_drift = sync_registry_hashes(reg, reg_text)
    if new_reg_text != reg_text:
        if args.check:
            drift.append(f"registry/voices.json: profile content_hash out of date "
                         f"({'; '.join(hash_drift)})")
        else:
            reg_path.write_text(new_reg_text)
            wrote.append("registry/voices.json (content_hash)")

    # Markdown sites.
    for rel, renderer in MD_SITES.items():
        path = repo / rel
        if not path.exists():
            drift.append(f"{rel}: file not found")
            continue
        text = path.read_text()
        rendered = renderer(reg)
        new_text = replace_marked_block(text, rendered, rel)
        if new_text != text:
            if args.check:
                drift.append(f"{rel}: roster block out of date")
            else:
                path.write_text(new_text)
                wrote.append(rel)

    # dispatch.config.example.json.
    dc_path = repo / DISPATCH_CONFIG
    if dc_path.exists():
        text = dc_path.read_text()
        new_text = render_dispatch_config(reg, text)
        if new_text != text:
            if args.check:
                drift.append(f"{DISPATCH_CONFIG}: voices/excluded-comment out of date")
            else:
                dc_path.write_text(new_text)
                wrote.append(DISPATCH_CONFIG)
    else:
        drift.append(f"{DISPATCH_CONFIG}: file not found")

    if args.check:
        if drift:
            print("gen_roster_docs --check: DRIFT")
            for d in drift:
                print(f"  - {d}")
            return 1
        print("gen_roster_docs --check: all roster blocks in sync with registry")
        return 0

    if wrote:
        print("gen_roster_docs: wrote")
        for w in wrote:
            print(f"  - {w}")
    else:
        print("gen_roster_docs: all sites already in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
