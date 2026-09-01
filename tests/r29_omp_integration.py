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

import importlib.util
import os
import re
import json
import shutil
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


def run(argv: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=120, env=env)


def init(project: Path, *extra: str) -> subprocess.CompletedProcess:
    return run([
        "uv", "run", "--script", str(SCRIPTS / "colosseum_init.py"),
        str(project), "--harness", "omp", *extra,
    ])


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    quickstart = (REPO / "QUICKSTART.md").read_text()
    documented_skills = (
        "colosseum-intent",
        "colosseum-reverse-intent",
        "colosseum-adversarial",
        "colosseum-verify",
        "colosseum-code-adversarial",
        "colosseum-compose",
        "colosseum-change",
    )
    missing_command_forms = [
        name for name in documented_skills
        if f"/{name}" not in quickstart or f"/skill:{name}" not in quickstart
    ]
    check("quickstart pairs Claude Code and OMP skill commands",
          not missing_command_forms, ", ".join(missing_command_forms))
    agent_reference_patterns = (
        re.compile(r"`(colosseum-[a-z][a-z0-9-]+)`\s+(?:agent|wrapper)", re.I),
        re.compile(r"(?:agent|wrapper)\s+`(colosseum-[a-z][a-z0-9-]+)`", re.I),
        re.compile(
            r"\b[a-z_]*agent\s*(?::[^=\n]+)?=\s*[\"']"
            r"(colosseum-[a-z][a-z0-9-]+)[\"']",
            re.I,
        ),
        re.compile(r"installed\s+`(colosseum-[a-z][a-z0-9-]+)`", re.I),
        re.compile(
            r"agent\s*=\s*[\"'](colosseum-[a-z][a-z0-9-]+)[\"']",
            re.I,
        ),
    )
    reference_sources = [REPO / "QUICKSTART.md"]
    reference_sources.extend(
        path for path in sorted((REPO / "skills").rglob("*"))
        if path.is_file() and (path.name == "SKILL.md" or path.suffix == ".py")
    )
    explicit_agent_refs: set[str] = set()
    for source in reference_sources:
        content = source.read_text()
        for pattern in agent_reference_patterns:
            explicit_agent_refs.update(pattern.findall(content))
    installed_agent_names = {Path(name).stem for name in canonical_agents}
    missing_agent_wrappers = sorted(explicit_agent_refs - installed_agent_names)
    check("every explicitly named OMP agent has a wrapper",
          not missing_agent_wrappers, ", ".join(missing_agent_wrappers))
    canonical_mcp = json.loads((REPO / "templates" / "omp-mcp.json").read_text())
    canonical_dispatch = json.loads(
        (SCRIPTS / "dispatch.config.example.json").read_text())

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
            source = (canonical / "SKILL.md").read_text()
            frontmatter_end = source.find("\n---\n", len("---\n")) + len("\n---\n")
            installed = (installed_skills / name / "SKILL.md").read_text()
            if name == "colosseum-adversarial":
                preserved = (
                    installed.startswith(source[:frontmatter_end])
                    and "### OMP-native agent fan-out" in installed
                    and "## Step 5: Quint-adversarial trace generation" in installed
                    and "OMP-EXCLUDE-" not in installed
                )
            else:
                preserved = (installed.startswith(source[:frontmatter_end])
                             and installed.endswith(source[frontmatter_end:]))
            check(f"OMP skill {name} preserves its applicable source body",
                  preserved)
            check(f"OMP skill {name} requires native dispatch",
                  "## OMP deployment boundary" in installed
                  and "Never invoke `opencode`" in installed)
        omp_reverse_intent = (
            installed_skills / "colosseum-reverse-intent" / "SKILL.md"
        ).read_text()
        normalized_reverse_intent = " ".join(omp_reverse_intent.split())
        check("OMP reverse-intent remains self-executing",
              "Execute its workflow in the current session" in normalized_reverse_intent
              and "Never derive an agent name from a skill name" in normalized_reverse_intent
              and "A self-executing skill does not require" in normalized_reverse_intent
              and not (installed_agents / "colosseum-reverse-intent.md").exists())
        omp_adversarial = (
            installed_skills / "colosseum-adversarial" / "SKILL.md"
        ).read_text()
        check("OMP adversarial skill dispatches only through native agents",
              "`colosseum-spec-adversary` through OMP `task`" in omp_adversarial
              and "### OMP-native agent fan-out" in omp_adversarial
              and "### OpenCode + spec-adversary agent (ReAct)"
              not in omp_adversarial
              and "opencode run --agent spec-adversary" not in omp_adversarial
              and "Claude Code Agent subagent" not in omp_adversarial
              and "colosseum_run.py" not in omp_adversarial
              and "critique_dispatch.py" not in omp_adversarial
              and "OpenCode writes its documented" not in omp_adversarial)
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
              == ["claude-agent", "gpt-5.6-sol", "glm-5.2", "kimi-k3"])
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
        code_adversary = (installed_agents / "colosseum-code-adversary.md").read_text()
        code_adversary_frontmatter = code_adversary.split("---", 2)[1]
        check("OMP code adversary is read-only",
              "tools: [read, grep, glob]" in code_adversary_frontmatter
              and "bash" not in code_adversary_frontmatter.lower()
              and "write" not in code_adversary_frontmatter.lower()
              and "edit" not in code_adversary_frontmatter.lower())

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

        managed_dispatch = json.loads(dispatch_path.read_text())
        managed_dispatch["target_spec"] = "/project-managed/intent.md"
        managed_dispatch["run_tag_prefix"] = "project-managed-tag"
        # A canonical roster change must reach an existing project. All four of
        # these keys are registry-generated by gen_roster_docs; a stale copy
        # cites a panel membership that no longer exists.
        managed_dispatch["omp_native"]["voices"] = [
            {"id": "stale-voice", "model": "stale/model", "family": "Stale",
             "calibration": "pending"}
        ]
        managed_dispatch["omp_native"]["route_hash"] = "sha256:0000000000000000"
        managed_dispatch["omp_native"]["profile"] = "canonical-4@sha256:staleprofile"
        managed_dispatch["_comment_canonical_panel"] = (
            "Canonical membership canonical-4@sha256:staleprofile.")
        managed_dispatch["_comment_excluded_voices"] = "stale excluded-voice provenance"
        managed_dispatch["default_variant"] = "max"
        managed_dispatch["voices"] = [
            {"id": "stale-voice", "model": "stale/model", "note": "stale"}
        ]
        dispatch_path.write_text(json.dumps(managed_dispatch, indent=2) + "\n")
        stale_rerun = init(project)
        stale_after = json.loads(dispatch_path.read_text())
        check("normal rerun leaves drifted registry keys alone (purely additive)",
              stale_rerun.returncode == 0
              and [v["id"] for v in stale_after["omp_native"]["voices"]] == ["stale-voice"]
              and [v["id"] for v in stale_after["voices"]] == ["stale-voice"]
              and "staleprofile" in stale_after["_comment_canonical_panel"]
              and stale_after["_comment_excluded_voices"]
              == "stale excluded-voice provenance")
        refreshed = init(project, "--refresh-omp")
        check("OMP targeted refresh exits 0",
              refreshed.returncode == 0, refreshed.stderr[-300:])
        check("targeted refresh restores canonical OMP agent",
              agent_path.read_bytes()
              == canonical_agents["colosseum-spec-adversary.md"].read_bytes())
        refreshed_skill = skill_path.read_text()
        check("targeted refresh restores OMP dispatch boundary",
              "## OMP deployment boundary" in refreshed_skill
              and "Never invoke `opencode`" in refreshed_skill
              and "skill-local-change" not in refreshed_skill)
        refreshed_mcp = json.loads(mcp_path.read_text())
        check("targeted refresh restores conflicting Colosseum MCP server",
              refreshed_mcp["mcpServers"]["kani"] == canonical_mcp["mcpServers"]["kani"])
        check("targeted refresh preserves unrelated MCP server",
              refreshed_mcp["mcpServers"]["custom"]["command"] == "custom-server")
        refreshed_dispatch = json.loads(dispatch_path.read_text())
        check("targeted refresh preserves project dispatch",
              refreshed_dispatch["target_spec"] == "/project-managed/intent.md"
              and refreshed_dispatch["run_tag_prefix"] == "project-managed-tag")
        check("targeted refresh restores the canonical OMP route",
              [v["id"] for v in refreshed_dispatch["omp_native"]["voices"]]
              == [v["id"] for v in canonical_dispatch["omp_native"]["voices"]]
              and refreshed_dispatch["omp_native"]["route_hash"]
              == canonical_dispatch["omp_native"]["route_hash"])
        check("targeted refresh leaves no stale panel provenance",
              all(refreshed_dispatch[key] == canonical_dispatch[key]
                  for key in ("omp_native", "_comment_omp_native",
                              "_comment_canonical_panel", "voices",
                              "_comment_excluded_voices",
                              "default_variant", "_comment_variant"))
              and "staleprofile" not in json.dumps(refreshed_dispatch)
              and "stale excluded-voice provenance"
              not in json.dumps(refreshed_dispatch))
        check("targeted refresh restores the one-below-max effort policy",
              refreshed_dispatch["omp_native"]["thinking_policy"] == "one-below-max"
              and refreshed_dispatch["default_variant"] == "high"
              and all(v["dispatch_selector"] == f"{v['model']}:{v['thinking_level']}"
                      for v in refreshed_dispatch["omp_native"]["voices"]))

        forced = init(project, "--force")
        check("OMP init --force exits 0", forced.returncode == 0, forced.stderr[-300:])
        forced_mcp = json.loads(mcp_path.read_text())
        check("--force restores canonical OMP agent",
              agent_path.read_bytes()
              == canonical_agents["colosseum-spec-adversary.md"].read_bytes())
        forced_skill = skill_path.read_text()
        check("--force restores OMP dispatch boundary",
              "## OMP deployment boundary" in forced_skill
              and "Never invoke `opencode`" in forced_skill
              and "skill-local-change" not in forced_skill)
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
        check("OMP doctor omits OpenCode toolchain and plumbing checks",
              not any(item.get("category") == "toolchain"
                      and item.get("name") == "opencode"
                      for item in report.get("checks", []))
              and not any(item.get("category") == "plumbing"
                          for item in report.get("checks", [])))
        fake_bin = project / "fake-bin"
        fake_bin.mkdir()
        sentinel = project / "opencode-called"
        fake_opencode = fake_bin / "opencode"
        fake_opencode.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$OPENCODE_SENTINEL\"\n"
            "if [ \"$1\" = \"--version\" ]; then\n"
            "  printf '%s\\n' '1.18.5'\n"
            "  exit 0\n"
            "fi\n"
            "exit 99\n"
        )
        fake_opencode.chmod(0o755)
        guarded_env = {
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "OPENCODE_SENTINEL": str(sentinel),
        }
        generic_doctor = run([
            "uv", "run", "--script", str(SCRIPTS / "colosseum_doctor.py"),
            "--skip-home-drift", "--json",
        ], env=guarded_env)
        try:
            generic_report = json.loads(generic_doctor.stdout)
            generic_parsed = True
        except json.JSONDecodeError:
            generic_report = {}
            generic_parsed = False
        generic_tools = {
            item["name"]: item for item in generic_report.get("checks", [])
            if item.get("category") == "toolchain"
        }
        check("no-project doctor retains the OpenCode toolchain check",
              generic_parsed and sentinel.exists()
              and generic_tools.get("opencode", {}).get("status") == "ok",
              generic_doctor.stderr[-300:])
        sentinel.unlink(missing_ok=True)
        live_omp = run([
            "uv", "run", "--script", str(SCRIPTS / "colosseum_doctor.py"),
            "--project", str(project), "--skip-home-drift", "--live",
        ], env=guarded_env)
        check("OMP doctor rejects OpenCode --live probes without invoking them",
              live_omp.returncode == 2
              and "--live is unavailable for an OMP project" in live_omp.stderr
              and not sentinel.exists(),
              live_omp.stderr[-300:])
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

    # User-level OMP install: boundary-rendered skills + generated wrappers in
    # OMP's agent dir, and NO project-scoped artifacts (a user install must
    # never imply a project is scaffolded).
    with tempfile.TemporaryDirectory(prefix="r29-omp-user-") as td:
        agent_dir = Path(td) / "agent"
        # Hermetic HOME: the doctor's user-level checks read ~/.claude and
        # ~/.omp, so a real-machine HOME would make this block assert ambient
        # state and go red the day someone legitimately reinstalls the Claude
        # harness. uv's cache/interpreter dirs are pinned back to the real ones
        # so the sandboxed HOME does not trigger a re-download.
        env = {
            **os.environ,
            "HOME": td,
            "USERPROFILE": td,
            "PI_CODING_AGENT_DIR": str(agent_dir),
            "UV_CACHE_DIR": os.environ.get(
                "UV_CACHE_DIR", str(Path.home() / ".cache" / "uv")),
            "UV_PYTHON_INSTALL_DIR": os.environ.get(
                "UV_PYTHON_INSTALL_DIR",
                str(Path.home() / ".local" / "share" / "uv" / "python")),
        }
        user = run([
            "uv", "run", "--script", str(SCRIPTS / "colosseum_init.py"),
            "--user", "--harness", "omp",
        ], env=env)
        check("OMP user install exits 0", user.returncode == 0, user.stderr[-300:])
        check("user install writes every OMP agent wrapper",
              {p.name for p in (agent_dir / "agents").glob("*.md")}
              == set(canonical_agents))
        check("user install writes every Colosseum skill",
              {p.name for p in (agent_dir / "skills").glob("colosseum-*")}
              == set(canonical_skills))
        user_adversarial = (agent_dir / "skills" / "colosseum-adversarial"
                            / "SKILL.md").read_text()
        check("user-installed skill carries the OMP boundary",
              "## OMP deployment boundary" in user_adversarial
              and "Never invoke `opencode`" in user_adversarial)
        check("user-installed skill leaks no non-OMP transport",
              "opencode run" not in user_adversarial
              and "colosseum_run.py" not in user_adversarial
              and "OMP-EXCLUDE-" not in user_adversarial)
        check("user-installed boundary names no project-only agent path",
              ".omp/agents/colosseum-*.md" not in user_adversarial)
        check("user install ships no project-scoped artifact",
              not (agent_dir / "mcp.json").exists()
              and not (agent_dir / "skills" / "dispatch.json").exists()
              and not (Path(td) / ".colosseum").exists())
        rerun = run([
            "uv", "run", "--script", str(SCRIPTS / "colosseum_init.py"),
            "--user", "--harness", "omp",
        ], env=env)
        check("user install is idempotent without --force",
              rerun.returncode == 0 and "skip" in rerun.stdout)
        doctor_user = run([
            "uv", "run", "--script", str(SCRIPTS / "colosseum_doctor.py"), "--json",
        ], env=env)
        user_report = json.loads(doctor_user.stdout)
        user_checks = [c for c in user_report["checks"]
                       if c["category"].startswith("drift/omp-user")]
        check("doctor sees a clean user-level OMP install",
              bool(user_checks) and all(c["status"] == "ok" for c in user_checks),
              str([c for c in user_checks if c["status"] != "ok"]))
        check("doctor reports no Claude install for an OMP-only machine",
              not [c for c in user_report["checks"]
                   if c["category"].startswith("drift/claude")])
        (agent_dir / "skills" / "colosseum-verify" / "SKILL.md").write_text("drift\n")
        drifted_user = run([
            "uv", "run", "--script", str(SCRIPTS / "colosseum_doctor.py"), "--json",
        ], env=env)
        drifted_checks = [
            c for c in json.loads(drifted_user.stdout)["checks"]
            if c["category"] == "drift/omp-user-skills"
            and c["name"].endswith("colosseum-verify")
        ]
        check("doctor detects drift in a user-installed skill",
              len(drifted_checks) == 1 and drifted_checks[0]["status"] == "fail")

        # Pin the installer's ignore deterministically: a clean source tree
        # would make "no bytecode in the install" pass vacuously, so plant a
        # __pycache__ in the SOURCE, reinstall, and assert none is deployed.
        source_cache = REPO / "skills" / "colosseum-verify" / "__pycache__"
        planted = not source_cache.exists()
        try:
            source_cache.mkdir(parents=True, exist_ok=True)
            (source_cache / "probe.cpython-313.pyc").write_bytes(b"\x00probe")
            reinstall = run([
                "uv", "run", "--script", str(SCRIPTS / "colosseum_init.py"),
                "--user", "--harness", "omp", "--force",
            ], env=env)
            check("install copies no bytecode from a dirty source tree",
                  reinstall.returncode == 0
                  and not list((agent_dir / "skills").rglob("*.pyc"))
                  and not list((agent_dir / "skills").rglob("__pycache__")),
                  str(sorted(p.name for p in (agent_dir / "skills").rglob("*.pyc"))))
        finally:
            if planted:
                shutil.rmtree(source_cache, ignore_errors=True)
            else:
                (source_cache / "probe.cpython-313.pyc").unlink(missing_ok=True)
        # Running a skill's helper writes __pycache__ into the DEPLOYED tree.
        # The drift hash must not treat that as content, or merely using the
        # fan-out makes a clean install look drifted.
        cache = agent_dir / "skills" / "colosseum-adversarial" / "__pycache__"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "omp_fanout.cpython-313.pyc").write_bytes(b"\x00stale bytecode")
        cached_doctor = run([
            "uv", "run", "--script", str(SCRIPTS / "colosseum_doctor.py"), "--json",
        ], env=env)
        cached_checks = [
            c for c in json.loads(cached_doctor.stdout)["checks"]
            if c["category"] == "drift/omp-user-skills"
            and c["name"].endswith("colosseum-adversarial")
        ]
        check("bytecode in a deployed skill is not drift",
              len(cached_checks) == 1 and cached_checks[0]["status"] == "ok",
              str(cached_checks))

        # A project may deliberately keep NO local skills/agents and rely on
        # the user-level install. That is correct configuration, not drift --
        # but the copy that will actually be used must still be verified, or a
        # stale user artifact passes unchecked under --skip-home-drift.
        lean = Path(td) / "lean-project"
        (lean / ".colosseum").mkdir(parents=True)
        (lean / ".colosseum" / "harness").write_text("omp\n")
        (lean / ".omp").mkdir()
        shutil.copy2(SCRIPTS / "dispatch.config.example.json",
                     lean / ".colosseum" / "dispatch.json")

        def lean_report():
            proc = run([
                "uv", "run", "--script", str(SCRIPTS / "colosseum_doctor.py"),
                "--project", str(lean), "--skip-home-drift", "--json",
            ], env=env)
            return json.loads(proc.stdout)["checks"]

        lean_checks = lean_report()
        satisfied = [c for c in lean_checks if c["name"].startswith("user-wide ")]
        # Scope to the categories the user-wide fallback covers. MCP servers,
        # the resolver extension and panel profiles have NO user-level
        # equivalent, so this fixture omits them and they must still report.
        lean_bad = [c for c in lean_checks
                    if c["category"] in ("drift/omp-skills", "drift/omp-agents")
                    and c["status"] != "ok"]
        check("a project with no local skills is satisfied user-wide",
              len(satisfied) == len(canonical_agents) + len(canonical_skills)
              and not lean_bad,
              f"satisfied={len(satisfied)} bad={[c['name'] for c in lean_bad]}")
        check("artifacts with no user-level equivalent still report",
              {c["name"] for c in lean_checks
               if c["category"].startswith("drift/omp-") and c["status"] != "ok"}
              == {".omp/mcp.json",
                  ".omp/extensions/colosseum-panel-resolver.ts",
                  ".colosseum/panel-profiles.json"})

        tampered = agent_dir / "skills" / "colosseum-verify" / "SKILL.md"
        original = tampered.read_text()

        # Lean layout: no project-local skills/agents, recorded in
        # .colosseum/layout so a later refresh does not silently reinstate the
        # copies a project deliberately dropped. Recorded rather than inferred
        # from whether a user install exists -- inferring would make init
        # depend on ambient machine state and behave differently in CI.
        leanp = Path(td) / "lean-init"
        first = run([
            "uv", "run", "--script", str(SCRIPTS / "colosseum_init.py"),
            str(leanp), "--harness", "omp", "--lean",
        ], env=env)
        check("lean init exits 0", first.returncode == 0, first.stderr[-300:])
        check("lean init records the layout",
              (leanp / ".colosseum" / "layout").read_text().strip() == "lean")
        check("lean init writes no project-local skills or agents",
              not (leanp / ".omp" / "skills").exists()
              and not (leanp / ".omp" / "agents").exists())
        check("lean init still writes what only a project can own",
              (leanp / ".colosseum" / "dispatch.json").is_file()
              and (leanp / ".omp" / "mcp.json").is_file()
              and (leanp / ".omp" / "extensions"
                   / "colosseum-panel-resolver.ts").is_file()
              and (leanp / ".colosseum" / "panel-profiles.json").is_file())
        again = run([
            "uv", "run", "--script", str(SCRIPTS / "colosseum_init.py"),
            str(leanp), "--harness", "omp", "--refresh-omp",
        ], env=env)
        check("a refresh does not reinstate a lean project's local copies",
              again.returncode == 0
              and not (leanp / ".omp" / "skills").exists()
              and not (leanp / ".omp" / "agents").exists(),
              again.stdout[-200:])
        check("--lean is rejected for a non-OMP harness",
              run(["uv", "run", "--script", str(SCRIPTS / "colosseum_init.py"),
                   str(Path(td) / "nope"), "--lean"], env=env).returncode == 2)
        tampered.write_text(original + "tampered\n")
        drifted_user_checks = [
            c for c in lean_report()
            if c["name"] == "user-wide skills/colosseum-verify"
        ]
        tampered.write_text(original)
        check("a stale user-level copy is drift even under --skip-home-drift",
              len(drifted_user_checks) == 1
              and drifted_user_checks[0]["status"] == "fail",
              str(drifted_user_checks))

    check_dispatch_key_ownership()

    print()
    if FAILURES:
        print(f"R29: {len(FAILURES)} failure(s)")
        return 1
    print("R29: all assertions passed")
    return 0


def check_dispatch_key_ownership() -> None:
    """The ownership table must match what the generator actually writes.

    The recurring defect this guards is not a wrong value, it is an unnoticed
    membership change: a key gets added to the generator or to the refresh set
    and the other side is never updated. Rather than trust prose, poison every
    key in the canonical config with a sentinel, re-render, and see which keys
    the generator overwrites. That is the real "generated" set.
    """
    init = _load_module("colosseum_init", SCRIPTS / "colosseum_init.py")
    gen = _load_module("gen_roster_docs", SCRIPTS / "gen_roster_docs.py")
    reg = gen.load_registry(REPO / "registry" / "voices.json")

    canonical = json.loads((SCRIPTS / "dispatch.config.example.json").read_text())
    sentinel = "SENTINEL-NOT-GENERATED"
    poisoned = json.dumps({key: sentinel for key in canonical})
    rendered = json.loads(gen.render_dispatch_config(reg, poisoned))
    generated = {key for key, value in rendered.items() if value != sentinel}

    declared_generated = {k for k, origin, _ in init.DISPATCH_KEY_OWNERSHIP
                          if origin == "generated"}
    declared_authored = {k for k, origin, _ in init.DISPATCH_KEY_OWNERSHIP
                         if origin == "authored"}
    static_prose = set(init.STATIC_PROSE_DISPATCH_KEYS)

    check("every key declared 'generated' really is generated",
          declared_generated <= generated,
          f"declared but not generated: {sorted(declared_generated - generated)}")
    check("no key declared 'authored' is generated",
          not (declared_authored & generated),
          f"authored but generated: {sorted(declared_authored & generated)}")
    check("every generated key is either owned or declared static prose",
          generated == declared_generated | static_prose,
          f"unclassified generator keys: "
          f"{sorted(generated - declared_generated - static_prose)}")
    check("static-prose keys are not silently refreshed",
          not (static_prose & set(init.COLOSSEUM_OWNED_DISPATCH_KEYS)))
    check("the owned set is exactly the ownership table",
          set(init.COLOSSEUM_OWNED_DISPATCH_KEYS)
          == declared_generated | declared_authored)
    check("additive keys are a subset of the owned set",
          set(init.ADDITIVE_DISPATCH_KEYS)
          <= set(init.COLOSSEUM_OWNED_DISPATCH_KEYS))
    check("every owned key exists in the canonical config",
          set(init.COLOSSEUM_OWNED_DISPATCH_KEYS) <= set(canonical),
          f"missing: {sorted(set(init.COLOSSEUM_OWNED_DISPATCH_KEYS) - set(canonical))}")
    check("every owned key carries a stated reason",
          all(reason.strip() for _, _, reason in init.DISPATCH_KEY_OWNERSHIP))



if __name__ == "__main__":
    sys.exit(main())

