#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Regenerate OMP-native roster blocks and dispatch routes from voices.json."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO / "registry" / "voices.json"
BEGIN_CANONICAL = (
    "<!-- BEGIN GENERATED: voice-roster (source: registry/voices.json "
    "via scripts/gen_roster_docs.py - do not edit by hand) -->"
)
END_CANONICAL = "<!-- END GENERATED: voice-roster -->"
BEGIN_RE = re.compile(r"^\s*<!--\s*BEGIN GENERATED: voice-roster\b.*?-->\s*$")
END_RE = re.compile(r"^\s*<!--\s*END GENERATED: voice-roster\s*-->\s*$")
OMP_ROUTE_GRADES = frozenset(
    {"attested", "unattested", "degraded", "errored", "contaminated", "not-run"}
)
DISPATCH_CONFIG = "scripts/dispatch.config.example.json"


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    if not path.exists():
        sys.exit(f"FATAL: registry not found at {path}")
    return json.loads(path.read_text())


def voice_by_id(reg: dict, voice_id: str) -> dict:
    for voice in reg["voices"]:
        if voice["id"] == voice_id:
            return voice
    sys.exit(f"FATAL: profile references unknown voice id {voice_id!r}")


def profile_content_hash(profile: dict) -> str:
    normalized = {
        "voices": sorted(
            ({"id": voice["id"], "variant": voice.get("variant", "max")} for voice in profile["voices"]),
            key=lambda item: item["id"],
        )
    }
    blob = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def omp_route_hash(route: dict) -> str:
    normalized = {
        "agent": route["agent"],
        "thinking_policy": route["thinking_policy"],
        "voices": sorted(
            (
                {
                    "id": voice["id"],
                    "model": voice["model"],
                    "thinking_level": voice.get("thinking_level"),
                }
                for voice in route["voices"]
            ),
            key=lambda item: item["id"],
        ),
    }
    blob = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def profile_by_name(reg: dict, name: str) -> dict:
    for profile in reg["profiles"]:
        if profile["name"] == name:
            return profile
    sys.exit(f"FATAL: no profile named {name!r}")


def canonical_omp_voices(reg: dict) -> list[dict]:
    profile = profile_by_name(reg, "canonical-4")
    result = []
    for member in profile["voices"]:
        voice = voice_by_id(reg, member["id"])
        if not voice.get("omp_model"):
            sys.exit(f"FATAL: canonical voice {voice['id']!r} has no OMP model")
        result.append(voice)
    return result


def selector(voice: dict) -> str:
    level = voice.get("omp_thinking_level")
    return f"{voice['omp_model']}:{level}" if level else voice["omp_model"]


def render_adversarial_model_ids(reg: dict) -> str:
    return "\n".join(
        f"- `{selector(voice)}` - {voice['family']}; route grade `{voice['omp_route_grade']}`."
        for voice in canonical_omp_voices(reg)
    )


def render_code_adversarial_frontier(reg: dict) -> str:
    return ", ".join(
        f"`{selector(voice)}` ({voice['family']})" for voice in canonical_omp_voices(reg)
    )


def render_scripts_readme_roster(reg: dict) -> str:
    rows = [
        "| Voice id | OMP selector | Family | Status | OMP calibration | Route grade |",
        "|---|---|---|---|---|---|",
    ]
    for voice in reg["voices"]:
        if not voice.get("omp_model"):
            continue
        calibration = voice.get("omp_calibration", "pending")
        rows.append(
            f"| `{voice['id']}` | `{selector(voice)}` | {voice['family']} | "
            f"{voice['status']} | {calibration} | {voice.get('omp_route_grade', 'n/a')} |"
        )
    return "\n".join(rows)


def render_install_roster(reg: dict) -> str:
    profile = profile_by_name(reg, "canonical-4")
    lines = [
        f"**Canonical OMP panel (`{profile['name']}@{profile['content_hash']}`).**",
        "",
    ]
    for voice in canonical_omp_voices(reg):
        lines.append(
            f"- `{selector(voice)}` - {voice['family']}; "
            f"route grade `{voice['omp_route_grade']}`."
        )
    lines.extend(
        [
            "",
            "Confirm every selector in OMP's `/model` picker before a milestone run.",
        ]
    )
    return "\n".join(lines)


MD_SITES = {
    "skills/fv-adversarial/SKILL.md": render_adversarial_model_ids,
    "skills/fv-code-adversarial/SKILL.md": render_code_adversarial_frontier,
    "scripts/README.md": render_scripts_readme_roster,
    "INSTALL.md": render_install_roster,
}


def render_omp_native_config(reg: dict) -> dict:
    profile = profile_by_name(reg, "canonical-4")
    voices = []
    for voice in canonical_omp_voices(reg):
        calibration = voice.get("omp_calibration")
        route_grade = voice.get("omp_route_grade")
        if not calibration or route_grade not in OMP_ROUTE_GRADES:
            sys.exit(f"FATAL: canonical voice {voice['id']!r} has no complete OMP route")
        if "omp_thinking_level" not in voice:
            sys.exit(f"FATAL: canonical voice {voice['id']!r} has no omp_thinking_level")
        level = voice["omp_thinking_level"]
        voices.append(
            {
                "id": voice["id"],
                "model": voice["omp_model"],
                "family": voice["family"],
                "thinking_level": level,
                "dispatch_selector": selector(voice),
                "calibration": calibration,
                "route_grade": route_grade,
            }
        )
    route = {
        "profile": f"{profile['name']}@{profile['content_hash']}",
        "agent": "fv-spec-adversary",
        "thinking_policy": "one-below-max",
        "calibration": "pending" if any(v["calibration"] == "pending" for v in voices) else "cited",
        "voices": voices,
    }
    route["route_hash"] = omp_route_hash(route)
    return route


def replace_marked_block(text: str, rendered: str, site: str) -> str:
    lines = text.splitlines()
    begin_idx = end_idx = None
    for index, line in enumerate(lines):
        if begin_idx is None and BEGIN_RE.match(line):
            begin_idx = index
        elif begin_idx is not None and END_RE.match(line):
            end_idx = index
            break
    if begin_idx is None or end_idx is None:
        sys.exit(f"FATAL: {site} is missing voice-roster markers")
    replacement = lines[:begin_idx] + [BEGIN_CANONICAL, rendered, END_CANONICAL] + lines[end_idx + 1 :]
    return "\n".join(replacement) + ("\n" if text.endswith("\n") else "")


def render_dispatch_config(reg: dict, current_text: str) -> str:
    current = json.loads(current_text)
    previous = current.get("omp_native") if isinstance(current.get("omp_native"), dict) else {}
    project_root = previous.get("project_root", current.get("project_root", "/absolute/path/to/project"))
    target_spec = previous.get(
        "target_spec", current.get("target_spec", "/absolute/path/to/project/.fv/intent.md")
    )
    route = render_omp_native_config(reg)
    route = {"project_root": project_root, "target_spec": target_spec, **route}
    return json.dumps({"omp_native": route}, indent=2, ensure_ascii=False) + "\n"


_HASH_RE = re.compile(r'("content_hash"\s*:\s*")sha256:[0-9a-f]+(")')


def sync_registry_hashes(reg: dict, registry_text: str) -> tuple[str, list[str]]:
    wanted = [profile_content_hash(profile) for profile in reg["profiles"]]
    drifts = [
        f"profile {profile['name']}: stored {profile.get('content_hash')} != {want}"
        for profile, want in zip(reg["profiles"], wanted)
        if profile.get("content_hash") != want
    ]
    found = _HASH_RE.findall(registry_text)
    if len(found) != len(wanted):
        drifts.append(f"registry has {len(found)} content_hash field(s), {len(wanted)} profile(s)")
    values = iter(wanted)
    return _HASH_RE.sub(lambda match: f"{match.group(1)}{next(values)}{match.group(2)}", registry_text), drifts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    registry = load_registry(repo / "registry" / "voices.json")
    for profile in registry["profiles"]:
        profile["content_hash"] = profile_content_hash(profile)

    drift: list[str] = []
    wrote: list[str] = []
    registry_path = repo / "registry" / "voices.json"
    registry_text = registry_path.read_text()
    new_registry_text, hash_drift = sync_registry_hashes(registry, registry_text)
    if new_registry_text != registry_text:
        if args.check:
            drift.append("registry/voices.json: " + "; ".join(hash_drift))
        else:
            registry_path.write_text(new_registry_text)
            wrote.append("registry/voices.json (content_hash)")

    for relative, renderer in MD_SITES.items():
        path = repo / relative
        if not path.exists():
            drift.append(f"{relative}: file not found")
            continue
        text = path.read_text()
        new_text = replace_marked_block(text, renderer(registry), relative)
        if new_text != text:
            if args.check:
                drift.append(f"{relative}: roster block out of date")
            else:
                path.write_text(new_text)
                wrote.append(relative)

    dispatch_path = repo / DISPATCH_CONFIG
    if dispatch_path.exists():
        text = dispatch_path.read_text()
        new_text = render_dispatch_config(registry, text)
        if new_text != text:
            if args.check:
                drift.append(f"{DISPATCH_CONFIG}: OMP route out of date")
            else:
                dispatch_path.write_text(new_text)
                wrote.append(DISPATCH_CONFIG)
    else:
        drift.append(f"{DISPATCH_CONFIG}: file not found")

    if args.check:
        if drift:
            print("gen_roster_docs --check: DRIFT")
            for item in drift:
                print(f"  - {item}")
            return 1
        print("gen_roster_docs --check: all OMP roster blocks in sync")
        return 0
    if wrote:
        print("gen_roster_docs: wrote")
        for item in wrote:
            print(f"  - {item}")
    else:
        print("gen_roster_docs: all sites already in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
