#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
install-agents — manage Colosseum agent distribution across harnesses.

Single source of truth: `colosseum/agents/spec-adversary-body.md` (canonical body, no frontmatter).
Per-harness wrappers in `colosseum/agents/` and `colosseum/agents/opencode/` prepend their
frontmatter to the canonical body.

USAGE

    install-agents.py build
        Regenerate dist files from canonical body + per-harness frontmatter.
        Run after editing the canonical body.

    install-agents.py lint
        Check that every dist file's body matches the canonical body.
        Exits non-zero on drift.

    install-agents.py install --harness opencode --target /path/to/.opencode/agent/
        Copy the OpenCode dist file into a project's .opencode/agent/ directory.

    install-agents.py install --harness claude-code --target ~/.claude/agents/
        Copy the Claude Code dist file into a Claude Code agents directory.

Each agent's frontmatter is defined inline in this script as a Python dict.
To add an agent, extend AGENTS below.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AGENTS_DIR = REPO / "agents"
CANONICAL_BODY = AGENTS_DIR / "spec-adversary-body.md"


# Per-agent, per-harness frontmatter.
# Each entry: {agent_name: {harness: {"dist_path": <relative-to-AGENTS_DIR>, "frontmatter": <yaml string>}}}
AGENTS = {
    "spec-adversary": {
        "canonical_body": "spec-adversary-body.md",
        "harnesses": {
            "claude-code": {
                "dist_path": "colosseum-spec-adversary.md",
                "frontmatter": """\
---
name: colosseum-spec-adversary
description: Adversarial reviewer for specifications. Given a spec and the intent it claims to encode, hunts for under-specification, over-specification, triviality, ambiguity, coverage gaps, contradictions, edge cases, and composition failures. Outputs a structured attack report. Use whenever a spec needs scrutiny before commitment — Quint modules, Lean theorem statements, Verus annotations, type-level invariants, or property-test specs.
tools: Read, Grep, Glob, Bash
---
""",
            },
            "opencode": {
                "dist_path": "opencode/spec-adversary.md",
                "frontmatter": """\
---
description: Adversarial reviewer for Colosseum specs. Reads target on demand; produces structured attack reports. Supports slice-aware dispatch (when invocation provides TARGET_SLICE) and full-spec dispatch (no TARGET_SLICE).
mode: all
temperature: 0.3
tools:
  read: true
  grep: true
  glob: true
  bash: false
  edit: false
  write: false
  webfetch: false
---
""",
            },
        },
    },
    "quint-spec-generator": {
        "canonical_body": "quint-spec-generator-body.md",
        "harnesses": {
            "claude-code": {
                "dist_path": "colosseum-quint-spec-generator.md",
                "frontmatter": """\
---
name: colosseum-quint-spec-generator
description: Generates a Quint protocol-layer specification from a validated intent document. One voice in a multi-model fan-out — different voices encode the same intent differently; the divergence is the methodology signal. Must produce files that typecheck, model-check clean against the safety invariant, and exhibit named reachability witnesses. Use after intent validation, before the implementation pyramid.
tools: Read, Grep, Glob, Bash, Write, Edit
---
""",
            },
            "opencode": {
                "dist_path": "opencode/quint-spec-generator.md",
                "frontmatter": """\
---
description: Generates Quint protocol-layer spec from intent. Reads intent + canonical Quint examples. Writes rcv.qnt + main.qnt + design-notes.md. Runs quint typecheck + quint run to self-verify before reporting status.
mode: all
temperature: 0.4
tools:
  read: true
  grep: true
  glob: true
  bash: true
  edit: true
  write: true
  webfetch: false
---
""",
            },
        },
    },
}


def read_canonical_body(agent_name: str) -> str:
    rel = AGENTS[agent_name]["canonical_body"]
    return (AGENTS_DIR / rel).read_text()


def strip_canonical_header_comment(body: str) -> str:
    """Strip the leading <!-- ... --> editor-instruction comment from the canonical body
    so it doesn't leak into the dist files (the comment is for editors of the body source,
    not for the agent runtime)."""
    if body.startswith("<!--"):
        end = body.find("-->")
        if end != -1:
            body = body[end + 3:].lstrip()
    return body


def build_dist_content(agent_name: str, harness: str) -> str:
    body = strip_canonical_header_comment(read_canonical_body(agent_name))
    frontmatter = AGENTS[agent_name]["harnesses"][harness]["frontmatter"]
    return frontmatter + "\n" + body


def cmd_build() -> int:
    """Write per-harness dist files from the canonical body + frontmatter."""
    n_written = 0
    for agent_name, agent_spec in AGENTS.items():
        for harness, hspec in agent_spec["harnesses"].items():
            dist_path = AGENTS_DIR / hspec["dist_path"]
            dist_path.parent.mkdir(parents=True, exist_ok=True)
            content = build_dist_content(agent_name, harness)
            existing = dist_path.read_text() if dist_path.exists() else None
            if existing == content:
                print(f"  [unchanged] {dist_path.relative_to(REPO)}")
                continue
            dist_path.write_text(content)
            n_written += 1
            print(f"  [wrote]     {dist_path.relative_to(REPO)} ({len(content)} bytes)")
    print(f"\nbuild complete: {n_written} file(s) written")
    return 0


def cmd_lint() -> int:
    """Check that each dist file's body matches the canonical body."""
    n_ok, n_drift = 0, 0
    for agent_name, agent_spec in AGENTS.items():
        for harness, hspec in agent_spec["harnesses"].items():
            dist_path = AGENTS_DIR / hspec["dist_path"]
            if not dist_path.exists():
                print(f"  [MISSING]   {dist_path.relative_to(REPO)}", file=sys.stderr)
                n_drift += 1
                continue
            expected = build_dist_content(agent_name, harness)
            actual = dist_path.read_text()
            if actual == expected:
                print(f"  [ok]        {dist_path.relative_to(REPO)}")
                n_ok += 1
            else:
                print(f"  [DRIFT]     {dist_path.relative_to(REPO)}", file=sys.stderr)
                # Show a tiny diff summary
                exp_lines = expected.splitlines()
                act_lines = actual.splitlines()
                print(f"             expected {len(exp_lines)} lines, got {len(act_lines)}", file=sys.stderr)
                n_drift += 1
    print(f"\nlint complete: {n_ok} ok, {n_drift} drift", file=sys.stderr if n_drift else sys.stdout)
    return 0 if n_drift == 0 else 1


def cmd_install(harness: str, target: Path, agent_name: str = "spec-adversary") -> int:
    """Copy the dist file for the given harness into a target directory."""
    hspec = AGENTS[agent_name]["harnesses"].get(harness)
    if hspec is None:
        print(f"unknown harness: {harness}. options: {sorted(AGENTS[agent_name]['harnesses'])}", file=sys.stderr)
        return 2
    dist_path = AGENTS_DIR / hspec["dist_path"]
    if not dist_path.exists():
        print(f"dist file missing — run `install-agents.py build` first: {dist_path}", file=sys.stderr)
        return 2
    target = target.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    dest = target / Path(hspec["dist_path"]).name
    shutil.copy2(dist_path, dest)
    print(f"installed {dist_path.relative_to(REPO)} → {dest}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("lint")
    sp_install = sub.add_parser("install")
    sp_install.add_argument("--harness", required=True, choices=["claude-code", "opencode"])
    sp_install.add_argument("--target", required=True, type=Path)
    sp_install.add_argument("--agent", default="spec-adversary")
    args = ap.parse_args()
    if args.cmd == "build":
        return cmd_build()
    if args.cmd == "lint":
        return cmd_lint()
    if args.cmd == "install":
        return cmd_install(args.harness, args.target, args.agent)
    return 2


if __name__ == "__main__":
    sys.exit(main())
