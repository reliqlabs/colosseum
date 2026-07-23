#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R29 - native OMP integration.

Exercises the generated OMP agent wrappers, project-local skill installation,
additive MCP configuration, force/idempotence behavior, frontmatter validation,
and doctor drift checks. Exit 0 pass, 1 fail.
"""
from __future__ import annotations

import os
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=120)


def init(project: Path, *extra: str) -> subprocess.CompletedProcess:
    return run([
        "uv", "run", "--script", str(SCRIPTS / "colosseum_init.py"),
        str(project), "--harness", "omp", *extra,
    ])


def main() -> int:
    lint = run(["uv", "run", "--script", str(SCRIPTS / "install-agents.py"), "lint"])
    check("agent wrappers match canonical bodies", lint.returncode == 0,
          (lint.stdout + lint.stderr)[-300:])

    validator = run([
        "uv", "run", "--script", str(SCRIPTS / "validate_frontmatter.py"),
        "--repo", str(REPO),
    ])
    check("frontmatter validator accepts OMP agents", validator.returncode == 0,
          (validator.stdout + validator.stderr)[-300:])

    canonical_agents = {
        path.name: path for path in sorted((REPO / "agents" / "omp").glob("*.md"))
    }
    canonical_skills = {
        path.name: path for path in sorted((REPO / "skills").glob("colosseum-*"))
        if (path / "SKILL.md").is_file()
    }
    canonical_mcp = json.loads((REPO / "templates" / "omp-mcp.json").read_text())

    with tempfile.TemporaryDirectory(prefix="r29-omp-") as td:
        project = Path(td) / "project"
        first = init(project)
        check("OMP init exits 0", first.returncode == 0, first.stderr[-300:])

        installed_agents = project / ".omp" / "agents"
        for name, canonical in canonical_agents.items():
            installed = installed_agents / name
            check(f"OMP init installs agent {name}",
                  installed.exists() and installed.read_bytes() == canonical.read_bytes())

        installed_skills = project / ".omp" / "skills"
        check("OMP init installs every Colosseum skill",
              {path.name for path in installed_skills.glob("colosseum-*")}
              == set(canonical_skills))
        for name, canonical in canonical_skills.items():
            check(f"OMP skill {name} includes SKILL.md",
                  (installed_skills / name / "SKILL.md").read_bytes()
                  == (canonical / "SKILL.md").read_bytes())
        check("OMP adversarial skill installs native fanout helper",
              (installed_skills / "colosseum-adversarial" / "omp_fanout.py").read_bytes()
              == (canonical_skills["colosseum-adversarial"] / "omp_fanout.py").read_bytes())

        mcp_path = project / ".omp" / "mcp.json"
        installed_mcp = json.loads(mcp_path.read_text())
        check("OMP MCP schema installed",
              installed_mcp.get("$schema") == canonical_mcp["$schema"])
        check("all Colosseum MCP servers installed",
              installed_mcp.get("mcpServers") == canonical_mcp["mcpServers"])
        check("OMP scaffold ships no .opencode artifacts",
              not (project / ".opencode").exists())
        check("OMP scaffold omits opencode_dispatch.py",
              not (project / ".colosseum" / "scripts" / "opencode_dispatch.py").exists())
        for name in ("check_ledger_references.py", "check_evidence_records.py"):
            script = project / ".colosseum" / "scripts" / name
            check(f"OMP init installs executable project script {name}",
                  script.exists() and os.access(script, os.X_OK))
        dispatch_path = project / ".colosseum" / "dispatch.json"
        dispatch = json.loads(dispatch_path.read_text())
        check("OMP init installs native canonical voice routes",
              [voice["id"] for voice in dispatch["omp_native"]["voices"]]
              == ["claude-agent", "gpt-5.6-sol", "glm-5.2", "kimi-k2.6"])
        check("OMP native routes are explicitly uncalibrated",
              dispatch["omp_native"]["calibration"] == "pending")
        check("OMP init installs the panel resolver extension",
              (project / ".omp" / "extensions" / "colosseum-panel-resolver.ts").read_bytes()
              == (REPO / "templates" / "omp-panel-resolver.ts").read_bytes())
        check("OMP init installs the panel profile",
              (project / ".colosseum" / "panel-profiles.json").read_bytes()
              == (REPO / "templates" / "omp-panel.json").read_bytes())
        check("OMP init creates the panels evidence dir",
              (project / ".colosseum" / "panels").is_dir())
        check("OMP init stamps the harness marker omp",
              (project / ".colosseum" / "harness").read_text().strip() == "omp")
        check("OMP init installs both panel agents",
              (installed_agents / "colosseum-panelist.md").exists()
              and (installed_agents / "colosseum-panel-synthesizer.md").exists())
        check("OMP init installs the panel skill engine + contract + roster",
              (installed_skills / "colosseum-panel" / "omp_panel.py").exists()
              and (installed_skills / "colosseum-panel" / "panel_contract.py").exists()
              and (installed_skills / "colosseum-panel" / "panel_roster.py").exists())

        adversary = (installed_agents / "colosseum-spec-adversary.md").read_text()
        check("OMP adversary is read-only",
              "tools: [read, grep, glob]" in adversary
              and "tools: [read, grep, glob, bash" not in adversary)

        # A normal rerun preserves owned files but fills a missing MCP definition.
        agent_path = installed_agents / "colosseum-spec-adversary.md"
        skill_path = installed_skills / "colosseum-intent" / "SKILL.md"
        agent_path.write_text("agent-local-change\n")
        skill_path.write_text("skill-local-change\n")
        installed_mcp["mcpServers"]["custom"] = {
            "type": "stdio", "command": "custom-server"
        }
        installed_mcp["mcpServers"]["kani"] = {
            "type": "stdio", "command": "custom-kani"
        }
        del installed_mcp["mcpServers"]["quint"]
        mcp_path.write_text(json.dumps(installed_mcp, indent=2) + "\n")

        second = init(project)
        check("OMP init rerun exits 0", second.returncode == 0, second.stderr[-300:])
        rerun_mcp = json.loads(mcp_path.read_text())
        check("normal rerun preserves changed OMP agent",
              agent_path.read_text() == "agent-local-change\n")
        check("normal rerun preserves changed OMP skill",
              skill_path.read_text() == "skill-local-change\n")
        check("normal rerun preserves conflicting MCP server",
              rerun_mcp["mcpServers"]["kani"]["command"] == "custom-kani")
        check("normal rerun restores missing MCP server",
              rerun_mcp["mcpServers"]["quint"] == canonical_mcp["mcpServers"]["quint"])
        check("normal rerun preserves unrelated MCP server",
              rerun_mcp["mcpServers"]["custom"]["command"] == "custom-server")

        forced = init(project, "--force")
        check("OMP init --force exits 0", forced.returncode == 0, forced.stderr[-300:])
        forced_mcp = json.loads(mcp_path.read_text())
        check("--force restores canonical OMP agent",
              agent_path.read_bytes()
              == canonical_agents["colosseum-spec-adversary.md"].read_bytes())
        check("--force restores canonical OMP skill",
              skill_path.read_bytes()
              == (canonical_skills["colosseum-intent"] / "SKILL.md").read_bytes())
        check("--force restores conflicting Colosseum MCP server",
              forced_mcp["mcpServers"]["kani"] == canonical_mcp["mcpServers"]["kani"])
        check("--force preserves unrelated MCP server",
              forced_mcp["mcpServers"]["custom"]["command"] == "custom-server")

        doctor = run([
            "uv", "run", "--script", str(SCRIPTS / "colosseum_doctor.py"),
            "--project", str(project), "--skip-home-drift", "--json",
        ])
        try:
            report = json.loads(doctor.stdout)
            parsed = True
        except json.JSONDecodeError:
            report = {}
            parsed = False
        check("OMP doctor emits JSON", parsed, doctor.stderr[-300:])
        omp_checks = [
            item for item in report.get("checks", [])
            if item.get("category", "").startswith("drift/omp")
        ]
        # per-agent + per-skill + dispatch(1) + mcp(1) + per-mcp-server + panel(2)
        expected_checks = len(canonical_agents) + len(canonical_skills) + 2 + len(
            canonical_mcp["mcpServers"]
        ) + 2
        check("OMP doctor checks every installed artifact",
              len(omp_checks) == expected_checks,
              f"expected={expected_checks} actual={len(omp_checks)}")
        check("OMP doctor reports clean project integration",
              bool(omp_checks) and all(item["status"] == "ok" for item in omp_checks),
              str([item for item in omp_checks if item["status"] != "ok"]))
        project_fails = [item for item in report.get("checks", [])
                         if item.get("category") == "drift/project"
                         and item["status"] != "ok"]
        check("OMP-only scaffold has no project-drift failures (harness-aware doctor)",
              not project_fails, project_fails)

        dispatch["omp_native"]["voices"][0]["model"] = "drifted/model"
        dispatch_path.write_text(json.dumps(dispatch, indent=2) + "\n")
        route_drifted = run([
            "uv", "run", "--script", str(SCRIPTS / "colosseum_doctor.py"),
            "--project", str(project), "--skip-home-drift", "--json",
        ])
        route_report = json.loads(route_drifted.stdout)
        route_checks = [
            item for item in route_report["checks"]
            if item["category"] == "drift/omp-dispatch"
        ]
        check("OMP doctor detects native route drift",
              len(route_checks) == 1 and route_checks[0]["status"] == "fail")
        restored = init(project, "--force")
        check("OMP init --force restores native route drift",
              restored.returncode == 0, restored.stderr[-300:])

        agent_path.write_text("drift\n")
        drifted = run([
            "uv", "run", "--script", str(SCRIPTS / "colosseum_doctor.py"),
            "--project", str(project), "--skip-home-drift", "--json",
        ])
        drift_report = json.loads(drifted.stdout)
        drift_checks = [
            item for item in drift_report["checks"]
            if item["category"] == "drift/omp-agents"
            and item["name"].endswith("colosseum-spec-adversary.md")
        ]
        check("OMP doctor detects agent drift",
              len(drift_checks) == 1 and drift_checks[0]["status"] == "fail")

    print()
    if FAILURES:
        print(f"R29: {len(FAILURES)} failure(s)")
        return 1
    print("R29: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
