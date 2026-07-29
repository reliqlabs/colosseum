#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
colosseum_init - scaffold a project for the Colosseum adversarial/verify loop (C4).

    colosseum_init.py <project-path> [--target-spec PATH]
        [--harness claude-code|omp] [--force|--refresh-omp]

Every scaffold receives the canonical `.colosseum/` evidence directories. A
Claude Code scaffold receives OpenCode adversarial agents and dispatch
machinery. An OMP scaffold receives only project-local OMP agents and skills,
then merges the Colosseum MCP servers into `.omp/mcp.json`.

Idempotent: an existing owned file or directory is never clobbered without
`--force`. OMP MCP installation is additive: unrelated server definitions are
preserved, missing Colosseum servers are added, and `--force` replaces only
conflicting Colosseum server definitions.

Exit 0 on success, 1 on a scaffold error.
"""
from __future__ import annotations

import argparse
import json
import os
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
    "code-adversary": "colosseum-code-adversary.md",
    "panelist": "colosseum-panelist.md",
    "panel-synthesizer": "colosseum-panel-synthesizer.md",
}
OMP_PANEL_PROFILE = REPO / "templates" / "omp-panel.json"
OMP_PANEL_RESOLVER = REPO / "templates" / "omp-panel-resolver.ts"

OMP_SKILL_BOUNDARY = """\
## OMP deployment boundary

This is an OMP-installed skill. Invoke Colosseum agents only through OMP-native
`task` or `eval` `agent()` calls, naming the `colosseum-*` agent directly and
letting OMP resolve it: wrappers install either project-locally
(`<project>/.omp/agents/`) or user-wide (`~/.omp/agent/agents/`), and a
user-level wrapper is discovered even in a project with no Colosseum scaffold.
Never invoke `opencode`, OpenCode agents, Claude Code's Agent tool, or a
single-shot model API from this skill. The renderer omits executable non-OMP
transport sections. Do not revive or follow a non-OMP route from residual
reference text. If OMP cannot resolve the named agent from any location, stop
and report the installation defect rather than substituting another transport.

"""
OMP_EXCLUDE_START = "<!-- OMP-EXCLUDE-START -->"
OMP_EXCLUDE_END = "<!-- OMP-EXCLUDE-END -->"
OMP_EXCLUDE_ROW = "<!-- OMP-EXCLUDE-ROW -->"

# Ownership of every Colosseum-managed key in <project>/.colosseum/dispatch.json.
# THIS TABLE IS THE SOURCE OF TRUTH — prose describing the set has drifted from
# it three times, so nothing restates the membership or the count. Each row is
# (key, origin, why it is owned). `origin` is verified mechanically by
# tests/r29: "generated" keys MUST be emitted by gen_roster_docs'
# render_dispatch_config, "authored" keys MUST NOT be.
DISPATCH_KEY_OWNERSHIP: tuple[tuple[str, str, str], ...] = (
    ("omp_native", "generated",
     "OMP-native route: per-voice models, effort, and route_hash"),
    ("_comment_omp_native", "generated",
     "provenance note bound to the route block"),
    ("_comment_canonical_panel", "generated",
     "canonical-<n>@<content_hash> membership pin a run may cite"),
    ("voices", "generated",
     "OpenCode voice roster derived from the canonical profile"),
    ("_comment_excluded_voices", "generated",
     "excluded and specialist voice rationale, derived from voice status"),
    ("default_variant", "authored",
     "OpenCode effort; one-below-max is `high` because OpenCode exposes only high/max"),
    ("_comment_variant", "authored",
     "explains the effort default and that calibration evidence predates it"),
)

# Emitted by render_dispatch_config but deliberately NOT refreshed: static
# prose with no registry or effort input. Declared so the r29 check can tell
# "intentionally excluded" from "a new generator key nobody classified".
STATIC_PROSE_DISPATCH_KEYS: tuple[str, ...] = (
    "_comment_top",
    "_comment_claude_voice",
)

# Filled on a plain rerun when missing; the rest move only under --refresh-omp.
ADDITIVE_DISPATCH_KEYS: tuple[str, ...] = ("omp_native", "_comment_omp_native")
COLOSSEUM_OWNED_DISPATCH_KEYS: tuple[str, ...] = tuple(
    key for key, _, _ in DISPATCH_KEY_OWNERSHIP)


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

def _remove_owned_path(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        path.unlink()
    else:
        shutil.rmtree(path)


def build_dispatch_json(project: Path, target_spec: Path) -> str:
    cfg = json.loads(CONFIG_EXAMPLE.read_text())
    cfg["project_root"] = str(project)
    cfg["target_spec"] = str(target_spec)
    return json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"


def install_dispatch_config(project: Path, target_spec: Path, force: bool,
                            refresh_omp: bool,
                            results: list[tuple[str, Path]]) -> list[str]:
    """Install the shared config, additively introducing OMP-native routes.

    Key ownership is DECLARED in `DISPATCH_KEY_OWNERSHIP`, not restated here:
    this docstring has drifted from the real set three times, so the table is
    the single source of truth and `tests/r29` checks it against the generator
    mechanically. Read the table for which keys are owned and why.

    A plain rerun stays purely additive: it fills a MISSING `omp_native` block
    and touches nothing else. `--refresh-omp` additionally rewrites every
    Colosseum-owned key to canonical, so a roster or effort change can reach an
    existing project instead of leaving a copy that cites a membership and an
    operating point which no longer exist. That is safe precisely because
    `--refresh-omp` refuses any non-OMP scaffold: an OMP scaffold ships no
    `opencode_dispatch.py`, so nothing in it consumes the OpenCode-facing keys
    and they are provenance rather than a live dispatch plan. Project-owned
    fields (`target_spec`, `run_tag_prefix`, `slices`, `context_appendix`,
    `env_passthrough`, ...) are preserved either way.
    """
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
    for key in ADDITIVE_DISPATCH_KEYS:
        if key not in current:
            current[key] = canonical[key]
            changed = True
    if refresh_omp:
        for key in COLOSSEUM_OWNED_DISPATCH_KEYS:
            if key in canonical and current.get(key) != canonical[key]:
                current[key] = canonical[key]
                changed = True
    if changed:
        dest.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n")
        results.append(("updated", dest))
    else:
        results.append(("skip", dest))
    return errors


def install_agents(agent_dir: Path, harness: str,
                   agent_files: dict[str, str], force: bool,
                   results: list[tuple[str, Path]]) -> list[str]:
    errors: list[str] = []
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


def render_omp_skill(source: Path) -> str:
    """Inject OMP's dispatch rule and omit non-OMP execution sections."""
    content = (source / "SKILL.md").read_text()
    content = "".join(
        line for line in content.splitlines(keepends=True)
        if OMP_EXCLUDE_ROW not in line
    )
    starts = content.count(OMP_EXCLUDE_START)
    ends = content.count(OMP_EXCLUDE_END)
    if starts != ends:
        raise ValueError(
            f"{source / 'SKILL.md'}: unmatched OMP exclusion marker"
        )
    while OMP_EXCLUDE_START in content:
        before, _, remainder = content.partition(OMP_EXCLUDE_START)
        _, _, after = remainder.partition(OMP_EXCLUDE_END)
        content = before + after
    if not content.startswith("---\n"):
        raise ValueError(f"{source / 'SKILL.md'}: missing YAML frontmatter")
    end = content.find("\n---\n", len("---\n"))
    if end < 0:
        raise ValueError(f"{source / 'SKILL.md'}: unterminated YAML frontmatter")
    frontmatter_end = end + len("\n---\n")
    return content[:frontmatter_end] + "\n" + OMP_SKILL_BOUNDARY + content[frontmatter_end:]


def install_omp_skills(skills_dir: Path, force: bool,
                       results: list[tuple[str, Path]]) -> None:
    """Render each Colosseum skill into `skills_dir` with the OMP boundary.

    Always a rendered COPY, never a symlink: the boundary injection and the
    non-OMP section stripping are deployment-time transforms, so a link back
    to the generic source would ship live `opencode` instructions into an OMP
    session. That is the exact leak the boundary exists to prevent.

    Python bytecode is never copied. A `__pycache__` present in the source at
    deploy time would otherwise be baked into the installed tree, and the
    doctor's tree hash would then report drift against a later, clean source.
    """
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
        shutil.copytree(source, dest,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        (dest / "SKILL.md").write_text(render_omp_skill(source))
        results.append(("overwrote" if existed else "wrote", dest))


def install_omp_mcp(project: Path, force: bool, replace_invalid: bool,
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
        if not replace_invalid:
            errors.append(f"{dest}: invalid JSON ({exc}); use --force to replace it")
            return errors
        dest.write_text(json.dumps(canonical, indent=2) + "\n")
        results.append(("overwrote", dest))
        return errors

    servers = current.get("mcpServers")
    if not isinstance(servers, dict):
        if not replace_invalid:
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


def omp_user_agent_dir() -> Path:
    """OMP's user-level agent dir, honouring profile and env overrides.

    Asks OMP itself (`omp config path`) so `OMP_PROFILE` and
    `PI_CODING_AGENT_DIR` resolve exactly as the running harness resolves
    them; falls back to the documented defaults when OMP is not on PATH.
    NOTE: this path is profile-scoped, so a `--profile <name>` session reads a
    different tree. Install once per profile you actually use.
    """
    try:
        proc = subprocess.run(["omp", "config", "path"],
                              capture_output=True, text=True, timeout=60)
        out = proc.stdout.strip()
        if proc.returncode == 0 and out:
            return Path(out).expanduser()
    except (OSError, subprocess.TimeoutExpired):
        pass
    env = os.environ.get("PI_CODING_AGENT_DIR")
    return Path(env).expanduser() if env else Path.home() / ".omp" / "agent"


def run_user_install(force: bool) -> int:
    """Install the boundary-rendered skills and OMP agent wrappers user-wide.

    Deliberately installs ONLY the project-independent artifacts. Everything
    that names a specific project -- dispatch.json (project_root, target_spec,
    slices), panel-profiles.json, the panel-resolver extension, the
    `.colosseum/` evidence tree -- stays project-local, so a user-level install
    never implies a project is scaffolded. A skill invoked in an unscaffolded
    root fails closed on the missing dispatch config, which is the intended
    behaviour: better a clear stop than a silent fallback to another transport.
    """
    agent_dir = omp_user_agent_dir()
    results: list[tuple[str, Path]] = []
    errors = install_agents(agent_dir / "agents", "omp",
                            OMP_AGENT_FILES, force, results)
    install_omp_skills(agent_dir / "skills", force, results)
    for action, path in results:
        print(f"  [{action:>9}] {path}")
    for err in errors:
        print(f"ERROR: {err}", file=sys.stderr)
    if errors:
        return 1
    print(f"\nInstalled Colosseum user-wide for OMP under {agent_dir}")
    print("  skills -> skills/colosseum-*  (boundary-rendered copies)")
    print("  agents -> agents/colosseum-*.md")
    print("\nNotes:")
    print("  1. This path is profile-scoped; rerun under each OMP_PROFILE you use.")
    print("  2. Project-specific artifacts still need a per-project scaffold:")
    print("       colosseum_init.py <project> --harness omp")
    print("  3. Rerun with --force after a canonical skill or agent change.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project", type=Path, nargs="?", default=None,
                    help="project root to scaffold (omit with --user)")
    ap.add_argument("--user", action="store_true",
                    help="install boundary-rendered skills and OMP agents user-wide "
                         "into OMP's agent dir instead of scaffolding a project")
    ap.add_argument("--target-spec", type=Path, default=None,
                    help="path to the spec/intent to attack "
                         "(default: <project>/.colosseum/intent.md)")
    ap.add_argument("--harness", choices=("claude-code", "omp"),
                    default="claude-code",
                    help="primary in-harness agent runtime (default: claude-code)")
    ap.add_argument("--force", action="store_true",
                    help="replace every Colosseum-owned artifact, including dispatch.json")
    ap.add_argument("--refresh-omp", action="store_true",
                    help="refresh OMP-owned artifacts without replacing dispatch.json")
    args = ap.parse_args()

    if args.user:
        if args.project is not None:
            ap.error("--user installs user-wide; do not also name a project")
        if args.refresh_omp:
            ap.error("--user has no project dispatch plan to preserve; use --force")
        if args.harness != "omp":
            ap.error("--user is OMP-only; pass --harness omp")
        return run_user_install(args.force)
    if args.project is None:
        ap.error("a project root is required unless --user is given")

    if args.refresh_omp and args.harness != "omp":
        ap.error("--refresh-omp requires --harness omp")

    project = args.project.resolve()
    marker = project / ".colosseum" / "harness"
    if (args.refresh_omp and marker.exists()
            and marker.read_text().strip() not in ("", "omp")):
        ap.error("--refresh-omp refuses to change a non-OMP scaffold; use --force")
    omp_force = args.force or args.refresh_omp
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
    errors = install_dispatch_config(project, target_spec, args.force,
                                     args.refresh_omp, results)

    # OpenCode agents are the calibrated reference transport for non-OMP harnesses.
    # An --harness omp scaffold is OMP-only and ships no .opencode/ artifacts.
    if ship_opencode:
        errors.extend(install_agents(
            project / ".opencode" / "agent", "opencode",
            OPENCODE_AGENT_FILES, args.force, results))
    if args.harness == "omp":
        errors.extend(install_agents(
            project / ".omp" / "agents", "omp",
            OMP_AGENT_FILES, omp_force, results))
        install_omp_skills(project / ".omp" / "skills", omp_force, results)
        errors.extend(install_omp_mcp(
            project, omp_force, replace_invalid=args.force, results=results))
        _copy_owned_file(OMP_PANEL_PROFILE,
                         project / ".colosseum" / "panel-profiles.json",
                         omp_force, results)
        _copy_owned_file(OMP_PANEL_RESOLVER,
                         project / ".omp" / "extensions" / "colosseum-panel-resolver.ts",
                         omp_force, results)

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
