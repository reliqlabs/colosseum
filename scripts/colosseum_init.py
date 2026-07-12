#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
colosseum_init — scaffold a project for the Colosseum adversarial/verify loop (C4).

    colosseum_init.py <project-path> [--target-spec PATH] [--force]

Creates the standard project layout and drops in the canonical dispatch machinery:

    <project>/.colosseum/
        attacks/     verify/     evidence/     scripts/
        scripts/opencode_dispatch.py     (copied from the repo canonical)
        dispatch.json                    (from dispatch.config.example.json,
                                          project_root + target_spec filled in)
    <project>/.opencode/agent/
        spec-adversary.md    quint-spec-generator.md   (via install-agents.py)

Idempotent: an existing file is never clobbered without --force; a re-run skips
what is already present and fills in what is missing. --force overwrites.

After scaffolding it prints the two manual steps init deliberately does not take:
registering the Claude Code agents into ~/.claude/agents, and running the doctor.

Exit 0 on success, 1 on a scaffold error (e.g. install-agents failed).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DISPATCH_SRC = REPO / "scripts" / "opencode_dispatch.py"
CONFIG_EXAMPLE = REPO / "scripts" / "dispatch.config.example.json"
INSTALL_AGENTS = REPO / "scripts" / "install-agents.py"
OPENCODE_AGENTS = ("spec-adversary", "quint-spec-generator")


def _put(path: Path, content: str, force: bool, results: list[tuple[str, Path]]) -> None:
    existed = path.exists()
    if existed and not force:
        results.append(("skip", path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    results.append(("overwrote" if existed else "wrote", path))


def build_dispatch_json(project: Path, target_spec: Path) -> str:
    cfg = json.loads(CONFIG_EXAMPLE.read_text())
    cfg["project_root"] = str(project)
    cfg["target_spec"] = str(target_spec)
    return json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"


def install_opencode_agents(project: Path, force: bool,
                            results: list[tuple[str, Path]]) -> list[str]:
    errors: list[str] = []
    agent_dir = project / ".opencode" / "agent"
    for agent in OPENCODE_AGENTS:
        dest = agent_dir / f"{agent}.md"
        existed = dest.exists()
        if existed and not force:
            results.append(("skip", dest))
            continue
        proc = subprocess.run(
            ["uv", "run", "--script", str(INSTALL_AGENTS), "install",
             "--harness", "opencode", "--target", str(agent_dir), "--agent", agent],
            capture_output=True, text=True)
        if proc.returncode != 0:
            errors.append(f"install-agents {agent}: {(proc.stderr or proc.stdout).strip()}")
        else:
            results.append(("overwrote" if existed else "wrote", dest))
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path, help="project root to scaffold")
    ap.add_argument("--target-spec", type=Path, default=None,
                    help="path to the spec/intent to attack "
                         "(default: <project>/.colosseum/intent.md)")
    ap.add_argument("--force", action="store_true", help="overwrite existing files")
    args = ap.parse_args()

    project = args.project.resolve()
    if not DISPATCH_SRC.exists() or not CONFIG_EXAMPLE.exists():
        print(f"FATAL: repo canonical files missing under {REPO / 'scripts'}", file=sys.stderr)
        return 1
    project.mkdir(parents=True, exist_ok=True)
    target_spec = (args.target_spec.resolve() if args.target_spec
                   else project / ".colosseum" / "intent.md")

    results: list[tuple[str, Path]] = []

    # Directory skeleton (mkdir is inherently idempotent).
    for sub in ("attacks", "verify", "evidence", "scripts"):
        (project / ".colosseum" / sub).mkdir(parents=True, exist_ok=True)

    # Canonical dispatch script + project config.
    _put(project / ".colosseum" / "scripts" / "opencode_dispatch.py",
         DISPATCH_SRC.read_text(), args.force, results)
    _put(project / ".colosseum" / "dispatch.json",
         build_dispatch_json(project, target_spec), args.force, results)

    # Both OpenCode agents.
    errors = install_opencode_agents(project, args.force, results)

    # Report.
    for action, path in results:
        try:
            shown = path.relative_to(project)
        except ValueError:
            shown = path
        print(f"  [{action:>9}] {shown}")
    for e in errors:
        print(f"  [    ERROR] {e}", file=sys.stderr)

    print(f"\nScaffolded {project}")
    if not args.target_spec:
        print(f"  target_spec defaults to {target_spec} — author it "
              f"(colosseum-intent / colosseum-reverse-intent) or re-run with --target-spec.")
    print("\nNext steps (init does NOT do these):")
    print(f"  1. Register the Claude Code agents (the claude-agent voice + failure classifier):")
    print(f"       {INSTALL_AGENTS.relative_to(REPO) if INSTALL_AGENTS.is_relative_to(REPO) else INSTALL_AGENTS} "
          f"install --harness claude-code --target ~/.claude/agents/")
    print(f"       (and symlink the skills per INSTALL.md §9)")
    print(f"  2. Edit .colosseum/dispatch.json: set run_tag_prefix, the voices roster "
          f"(from registry/voices.json), and the slice plan.")
    print(f"  3. Run the doctor against this project:")
    print(f"       scripts/colosseum_doctor.py --project {project}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
