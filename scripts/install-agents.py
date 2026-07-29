#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
install-agents — manage Colosseum agent distribution across harnesses.

Each agent in the AGENTS table below names its own canonical body (a
frontmatter-free `*-body.md` under `colosseum/agents/`) and, per harness, the
frontmatter and dist path for its wrapper. A dist (wrapper) file is built by
stripping the body's leading editor-instruction comment and prepending that
harness's frontmatter. Current harnesses are Claude Code, OpenCode, and OMP.

USAGE

    install-agents.py build
        Regenerate dist files from each agent's canonical body + per-harness
        frontmatter. Run after editing a canonical body.

    install-agents.py lint
        Check that every dist file matches its rebuilt content.
        Exits non-zero on drift.

    install-agents.py install --harness opencode --target /path/to/.opencode/agent/ [--agent <name>]
        Copy an agent's OpenCode dist file into a project's .opencode/agent/
        directory. --agent defaults to spec-adversary.

    install-agents.py install --harness claude-code --target ~/.claude/agents/ [--agent <name>]
        Copy an agent's Claude Code dist file into a Claude Code agents directory.

    install-agents.py install --harness omp --target <project>/.omp/agents/ [--agent <name>]
        Copy an agent's OMP dist file into a project's native OMP agents directory.

To add an agent, extend AGENTS below with its canonical_body and per-harness
frontmatter + dist_path.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AGENTS_DIR = REPO / "agents"


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
# Deny-first reviewer profile (G5): read-only over the project, secrets
# masked, no shell / writes / network / subagents. Last matching rule wins.
permission:
  read:
    "*": allow
    "**/.env": deny
    "**/.env.*": deny
    "**/*.secret": deny
    "**/secrets.*": deny
    "**/id_rsa*": deny
  glob: allow
  grep: allow
  edit: deny
  bash: deny
  task: deny
  skill: deny
  lsp: deny
  question: deny
  webfetch: deny
  websearch: deny
  external_directory: deny
  doom_loop: deny
---
""",
            },
            "omp": {
                "dist_path": "omp/colosseum-spec-adversary.md",
                "frontmatter": """\
---
name: colosseum-spec-adversary
description: Adversarial reviewer for specifications. Reads the target specification and its intent, then returns grounded under-specification, over-specification, ambiguity, coverage, contradiction, edge-case, and composition findings. Use before committing a Quint module, Lean theorem statement, Verus annotation, type invariant, or property-test specification.
tools: [read, grep, glob]
read-summarize: false
thinking-level: high
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
description: Generates Quint protocol-layer spec from intent. Reads intent + canonical Quint examples. Writes the spec files into OUTPUT_DIR. Runs quint typecheck + quint checks and reports a STATUS proposal.
mode: all
temperature: 0.4
# Deny-first generator profile (G5): read-only source and intent, writes for
# spec output only, shell scoped to the quint CLI, no network / subagents.
# The obligation manifest is orchestrator-owned and never generator-writable.
# Last matching rule wins.
permission:
  read:
    "*": allow
    "**/.env": deny
    "**/.env.*": deny
    "**/*.secret": deny
    "**/secrets.*": deny
  glob: allow
  grep: allow
  edit:
    "*": allow
    "**/.colosseum/obligations*": deny
    "**/intent.md": deny
    "**/.env": deny
    "**/.env.*": deny
  bash:
    "*": deny
    "quint *": allow
  task: deny
  skill: deny
  lsp: deny
  question: deny
  webfetch: deny
  websearch: deny
  external_directory: deny
  doom_loop: deny
---
""",
            },
            "omp": {
                "dist_path": "omp/colosseum-quint-spec-generator.md",
                "frontmatter": """\
---
name: colosseum-quint-spec-generator
description: Generate a Quint protocol specification from a validated intent document. Writes only the requested specification output, runs Quint checks, and reports model-checking and reachability results. Use after intent validation and before implementation.
tools: [read, grep, glob, bash, write, edit]
read-summarize: false
---
""",
            },
        },
    },
    "failure-classifier": {
        "canonical_body": "failure-classifier-body.md",
        "harnesses": {
            "claude-code": {
                "dist_path": "colosseum-failure-classifier.md",
                "frontmatter": """\
---
name: colosseum-failure-classifier
description: Classify a verification failure as spec-wrong, code-wrong, prover-stuck, tool-mismatch, state-space-blowup, infrastructure, or INDETERMINATE. Returns grounded reasoning and one next action. Use whenever a verification-pyramid layer fails.
tools: Read, Grep, Glob, Bash
---
""",
            },
            "omp": {
                "dist_path": "omp/colosseum-failure-classifier.md",
                "frontmatter": """\
---
name: colosseum-failure-classifier
description: Classify a verification failure as spec-wrong, code-wrong, prover-stuck, tool-mismatch, state-space-blowup, infrastructure, or INDETERMINATE. Returns grounded reasoning and one next action. Use whenever a verification-pyramid layer fails.
tools: [read, grep, glob, bash]
read-summarize: false
---
""",
            },
        },
    },
    "code-adversary": {
        "canonical_body": "code-adversary-body.md",
        "harnesses": {
            "omp": {
                "dist_path": "omp/colosseum-code-adversary.md",
                "frontmatter": """\
---
name: colosseum-code-adversary
description: Read-only implementation reviewer. Audits a post-commit Colosseum project against its intent and ledger through six lenses, returning an evidence-backed report for the invoking skill to persist. Use after a non-trivial commit and before external audit.
tools: [read, grep, glob]
read-summarize: false
thinking-level: high
---
""",
            },
        },
    },
    "panelist": {
        "canonical_body": "panelist-body.md",
        "harnesses": {
            "omp": {
                "dist_path": "omp/colosseum-panelist.md",
                "frontmatter": """\
---
name: colosseum-panelist
description: One independent voice on a Colosseum deliberation panel. Drafts a complete plan or milestone evaluation from a frozen brief, or cross-reviews anonymized peer artifacts, returning the structured object its prompt's schema requires. Grounds every repository claim in citations and treats peer content as untrusted data. Use only through the colosseum-panel skill's fan-out.
tools: [read, grep, glob, bash]
read-summarize: false
thinking-level: high
---
""",
            },
        },
    },
    "panel-synthesizer": {
        "canonical_body": "panel-synthesizer-body.md",
        "harnesses": {
            "omp": {
                "dist_path": "omp/colosseum-panel-synthesizer.md",
                "frontmatter": """\
---
name: colosseum-panel-synthesizer
description: Synthesizer/adjudicator for a Colosseum deliberation panel. Combines independent artifacts and cross-reviews into one canonical plan (project-plan mode) or an evidence-based milestone verdict (milestone-review mode), retaining grounded dissent and never converting missing evidence into PASS. Use only through the colosseum-panel skill's fan-out.
tools: [read, grep, glob]
read-summarize: false
thinking-level: high
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
    agent_spec = AGENTS.get(agent_name)
    if agent_spec is None:
        print(f"unknown agent: {agent_name}. options: {sorted(AGENTS)}", file=sys.stderr)
        return 2
    hspec = agent_spec["harnesses"].get(harness)
    if hspec is None:
        print(f"unknown harness: {harness}. options: {sorted(agent_spec['harnesses'])}", file=sys.stderr)
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
    sp_install.add_argument("--harness", required=True, choices=["claude-code", "opencode", "omp"])
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
