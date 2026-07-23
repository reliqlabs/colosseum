#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
colosseum_init - scaffold a project for the Colosseum adversarial/verify loop (C4).

    colosseum_init.py <project-path> [--target-spec PATH]
        [--harness claude-code|omp] [--force]

Every harness receives the canonical `.colosseum/` evidence directories,
OpenCode adversarial agents, and dispatch machinery. `--harness omp` also
installs project-local OMP agents and skills, then merges the Colosseum MCP
servers into `.omp/mcp.json`.

Idempotent: an existing owned file or directory is never clobbered without
`--force`. OMP MCP installation is additive: unrelated server definitions are
preserved, missing Colosseum servers are added, and `--force` replaces only
conflicting Colosseum server definitions.

Exit 0 on success, 1 on a scaffold error.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PROJECT_SCRIPT_NAMES = (
    "check_ledger_references.py",
    "check_evidence_records.py",
)
OPENCODE_SCRIPT_NAMES = (
    "opencode_dispatch.py",
)
CONFIG_EXAMPLE = REPO / "scripts" / "dispatch.config.example.json"
OMP_MCP_TEMPLATE = REPO / "templates" / "omp-mcp.json"
INSTALL_AGENTS = REPO / "scripts" / "install-agents.py"
OPENCODE_AGENT_FILES = {
    "spec-adversary": "spec-adversary.md",
    "quint-spec-generator": "quint-spec-generator.md",
}
OMP_AGENT_FILES = {
    "spec-adversary": "colosseum-spec-adversary.md",
    "quint-spec-generator": "colosseum-quint-spec-generator.md",
    "failure-classifier": "colosseum-failure-classifier.md",
    "panelist": "colosseum-panelist.md",
    "panel-synthesizer": "colosseum-panel-synthesizer.md",
}
OMP_PANEL_PROFILE = REPO / "templates" / "omp-panel.json"
OMP_PANEL_RESOLVER = REPO / "templates" / "omp-panel-resolver.ts"


def _put(path: Path, content: str, force: bool, results: list[tuple[str, Path]]) -> None:
    existed = path.exists()
    if existed and not force:
        results.append(("skip", path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    results.append(("overwrote" if existed else "wrote", path))


def _copy_owned_file(source: Path, dest: Path, force: bool,
                     results: list[tuple[str, Path]]) -> None:
    existed = dest.exists()
    if existed and not force:
        results.append(("skip", dest))
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    results.append(("overwrote" if existed else "wrote", dest))


def build_dispatch_json(project: Path, target_spec: Path) -> str:
    cfg = json.loads(CONFIG_EXAMPLE.read_text())
    cfg["project_root"] = str(project)
    cfg["target_spec"] = str(target_spec)
    return json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"


def install_dispatch_config(project: Path, target_spec: Path, force: bool,
                            results: list[tuple[str, Path]]) -> list[str]:
    """Install the shared config, additively introducing OMP-native routes."""
    errors: list[str] = []
    dest = project / ".colosseum" / "dispatch.json"
    canonical = json.loads(build_dispatch_json(project, target_spec))
    if not dest.exists():
        dest.write_text(json.dumps(canonical, indent=2, ensure_ascii=False) + "\n")
        results.append(("wrote", dest))
        return errors
    if force:
        dest.write_text(json.dumps(canonical, indent=2, ensure_ascii=False) + "\n")
        results.append(("overwrote", dest))
        return errors
    try:
        current = json.loads(dest.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        results.append(("skip", dest))
        print(f"WARN: {dest}: invalid JSON ({exc}); preserved; use --force to replace it",
              file=sys.stderr)
        return errors

    changed = False
    for key in ("omp_native", "_comment_omp_native"):
        if key not in current:
            current[key] = canonical[key]
            changed = True
    if changed:
        dest.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n")
        results.append(("updated", dest))
    else:
        results.append(("skip", dest))
    return errors


def install_agents(project: Path, harness: str, relative_dir: Path,
                   agent_files: dict[str, str], force: bool,
                   results: list[tuple[str, Path]]) -> list[str]:
    errors: list[str] = []
    agent_dir = project / relative_dir
    for agent, filename in agent_files.items():
        dest = agent_dir / filename
        existed = dest.exists()
        if existed and not force:
            results.append(("skip", dest))
            continue
        proc = subprocess.run(
            ["uv", "run", "--script", str(INSTALL_AGENTS), "install",
             "--harness", harness, "--target", str(agent_dir), "--agent", agent],
            capture_output=True, text=True)
        if proc.returncode != 0:
            errors.append(f"install-agents {harness}/{agent}: "
                          f"{(proc.stderr or proc.stdout).strip()}")
        else:
            results.append(("overwrote" if existed else "wrote", dest))
    return errors


def _remove_owned_path(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        path.unlink()
    else:
        shutil.rmtree(path)


def install_omp_skills(project: Path, force: bool,
                       results: list[tuple[str, Path]]) -> None:
    skills_dir = project / ".omp" / "skills"
    for source in sorted((REPO / "skills").glob("colosseum-*")):
        if not (source / "SKILL.md").is_file():
            continue
        dest = skills_dir / source.name
        existed = dest.exists() or dest.is_symlink()
        if existed and not force:
            results.append(("skip", dest))
            continue
        if existed:
            _remove_owned_path(dest)
        shutil.copytree(source, dest)
        results.append(("overwrote" if existed else "wrote", dest))


def install_omp_mcp(project: Path, force: bool,
                    results: list[tuple[str, Path]]) -> list[str]:
    errors: list[str] = []
    dest = project / ".omp" / "mcp.json"
    canonical = json.loads(OMP_MCP_TEMPLATE.read_text())
    existed = dest.exists()
    if not existed:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(canonical, indent=2) + "\n")
        results.append(("wrote", dest))
        return errors

    try:
        current = json.loads(dest.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        if not force:
            errors.append(f"{dest}: invalid JSON ({exc}); use --force to replace it")
            return errors
        dest.write_text(json.dumps(canonical, indent=2) + "\n")
        results.append(("overwrote", dest))
        return errors

    servers = current.get("mcpServers")
    if not isinstance(servers, dict):
        if not force:
            errors.append(f"{dest}: mcpServers is not an object; use --force to replace it")
            return errors
        current["mcpServers"] = {}
        servers = current["mcpServers"]

    changed = False
    if "$schema" not in current:
        current["$schema"] = canonical["$schema"]
        changed = True
    for name, config in canonical["mcpServers"].items():
        if name not in servers:
            servers[name] = config
            changed = True
        elif force and servers[name] != config:
            servers[name] = config
            changed = True

    if changed:
        dest.write_text(json.dumps(current, indent=2) + "\n")
        results.append(("updated" if existed else "wrote", dest))
    else:
        results.append(("skip", dest))
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path, help="project root to scaffold")
    ap.add_argument("--target-spec", type=Path, default=None,
                    help="path to the spec/intent to attack "
                         "(default: <project>/.colosseum/intent.md)")
    ap.add_argument("--harness", choices=("claude-code", "omp"),
                    default="claude-code",
                    help="primary in-harness agent runtime (default: claude-code)")
    ap.add_argument("--force", action="store_true",
                    help="replace owned files and conflicting Colosseum OMP entries")
    args = ap.parse_args()

    project = args.project.resolve()
    ship_opencode = args.harness != "omp"
    project_scripts = [REPO / "scripts" / name for name in PROJECT_SCRIPT_NAMES]
    if ship_opencode:
        project_scripts += [REPO / "scripts" / name for name in OPENCODE_SCRIPT_NAMES]
    required = [*project_scripts, CONFIG_EXAMPLE, INSTALL_AGENTS]
    if args.harness == "omp":
        required += [OMP_MCP_TEMPLATE, OMP_PANEL_PROFILE, OMP_PANEL_RESOLVER]
    missing = [path for path in required if not path.exists()]
    if missing:
        print(f"FATAL: canonical files missing: {missing}", file=sys.stderr)
        return 1
    project.mkdir(parents=True, exist_ok=True)
    target_spec = (args.target_spec.resolve() if args.target_spec
                   else project / ".colosseum" / "intent.md")

    results: list[tuple[str, Path]] = []

    # Directory skeleton (mkdir is inherently idempotent).
    for sub in ("attacks", "verify", "evidence", "scripts", "panels"):
        (project / ".colosseum" / sub).mkdir(parents=True, exist_ok=True)

    # Canonical project scripts + dispatch config.
    for source in project_scripts:
        _copy_owned_file(source, project / ".colosseum" / "scripts" / source.name,
                         args.force, results)
    errors = install_dispatch_config(project, target_spec, args.force, results)

    # OpenCode agents are the calibrated reference transport for non-OMP harnesses.
    # An --harness omp scaffold is OMP-only and ships no .opencode/ artifacts.
    if ship_opencode:
        errors.extend(install_agents(
            project, "opencode", Path(".opencode/agent"),
            OPENCODE_AGENT_FILES, args.force, results))
    if args.harness == "omp":
        errors.extend(install_agents(
            project, "omp", Path(".omp/agents"),
            OMP_AGENT_FILES, args.force, results))
        install_omp_skills(project, args.force, results)
        errors.extend(install_omp_mcp(project, args.force, results))
        _copy_owned_file(OMP_PANEL_PROFILE,
                         project / ".colosseum" / "panel-profiles.json",
                         args.force, results)
        _copy_owned_file(OMP_PANEL_RESOLVER,
                         project / ".omp" / "extensions" / "colosseum-panel-resolver.ts",
                         args.force, results)

    # Harness marker: lets the doctor apply the right drift class (an --harness
    # omp scaffold ships no .opencode artifacts).
    marker = project / ".colosseum" / "harness"
    want = args.harness + "\n"
    if not marker.exists():
        marker.write_text(want)
        results.append(("wrote", marker))
    elif marker.read_text() != want and args.force:
        marker.write_text(want)
        results.append(("overwrote", marker))
    else:
        results.append(("skip", marker))

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
    print("\nNext steps:")
    if args.harness == "omp":
        print(f"  1. Export COLOSSEUM={REPO} before starting OMP; also export "
              "VERUS_BIN, CHARON_BIN, and AENEAS_BIN for those optional layers.")
        print("  2. Start OMP in the project, run `/mcp reload`, then `/mcp test` "
              "for each installed server.")
        print("  3. Invoke skills as `/skill:colosseum-intent`, "
              "`/skill:colosseum-verify`, and similar.")
        next_step = 4
    else:
        print("  1. Register the Claude Code agents and symlink the skills per INSTALL.md §9.")
        next_step = 2
    if args.harness == "omp":
        print(f"  {next_step}. Confirm omp_native patterns in `/model`; edit "
              "run_tag_prefix and slices in .colosseum/dispatch.json.")
    else:
        print(f"  {next_step}. Edit .colosseum/dispatch.json: set run_tag_prefix, "
              "voices, and slices.")
    print(f"  {next_step + 1}. Run the doctor against this project:")
    doctor_flags = " --skip-home-drift" if args.harness == "omp" else ""
    print(f"       scripts/colosseum_doctor.py --project {project}{doctor_flags}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
