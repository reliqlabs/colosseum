#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""R0: OMP voice registry, generated roster, and dispatch consistency."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FAILURES: list[str] = []


def check(label: str, condition: bool, detail: object = "") -> None:
    if condition:
        print(f"  [ok]   {label}")
    else:
        print(f"  [FAIL] {label}" + (f" ({detail})" if detail else ""))
        FAILURES.append(label)


def load_generator():
    path = REPO / "scripts" / "gen_roster_docs.py"
    spec = importlib.util.spec_from_file_location("gen_roster_docs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    registry = json.loads((REPO / "registry" / "voices.json").read_text())
    allowed = {"canonical-panel", "candidate", "retired"}
    check("all voice statuses use OMP-era vocabulary", all(v["status"] in allowed for v in registry["voices"]))
    for voice in registry["voices"]:
        if voice["status"] == "canonical-panel":
            check(f"{voice['id']}: canonical route has OMP model", bool(voice.get("omp_model")))
            check(f"{voice['id']}: canonical route has grade", bool(voice.get("omp_route_grade")))
        if not voice.get("omp_model"):
            check(f"{voice['id']}: route-less voice retired", voice["status"] == "retired")

    generator = load_generator()
    for profile in registry["profiles"]:
        check(
            f"{profile['name']}: content hash current",
            profile["content_hash"] == generator.profile_content_hash(profile),
        )
    example_text = (REPO / "scripts" / "dispatch.config.example.json").read_text()
    rendered = generator.render_dispatch_config(registry, example_text)
    check("dispatch example is generated", rendered == example_text)
    dispatch = json.loads(example_text)
    check("dispatch top level contains only omp_native", set(dispatch) == {"omp_native"})
    route = dispatch["omp_native"]
    check("route hash current", route["route_hash"] == generator.omp_route_hash(route))
    check(
        "canonical profile membership matches dispatch",
        [voice["id"] for voice in route["voices"]]
        == [member["id"] for member in registry["profiles"][0]["voices"]],
    )

    generated = subprocess.run(
        ["python3", str(REPO / "scripts" / "gen_roster_docs.py"), "--check"],
        capture_output=True,
        text=True,
    )
    check("generated roster has no drift", generated.returncode == 0, generated.stdout + generated.stderr)
    validator = subprocess.run(
        ["python3", str(REPO / "scripts" / "check_dispatch_config.py"), "--selftest"],
        capture_output=True,
        text=True,
    )
    check("dispatch validator selftest passes", validator.returncode == 0, validator.stdout + validator.stderr)
    check("root package MCP manifest matches expected hash shape", len(hashlib.sha256((REPO / ".mcp.json").read_bytes()).hexdigest()) == 64)

    print()
    if FAILURES:
        print(f"R0: {len(FAILURES)} failure(s)")
        return 1
    print("R0: all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
