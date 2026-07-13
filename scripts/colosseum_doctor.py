#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
colosseum_doctor — offline preflight + drift diagnostics for a Colosseum install (C4).

Offline by default (no model calls, no money spent). It answers three questions:

  1. Is the toolchain present and pinned?  opencode / quint / cargo / lean / uv
     versions are compared against bom.json. A present-but-wrong version fails;
     an absent tool warns (a partial install is legitimate).

  2. Is the voice registry self-consistent?  Every profile's content_hash is
     recomputed and compared to the stored value, and the registry invariant is
     enforced: a canonical-panel voice with pending calibration is a failure.

  3. Is the provider plumbing in place, for free?  For each OpenCode voice in
     the canonical-4 profile: the provider is named in ~/.config/opencode/
     opencode.jsonc, required env vars are set, and any local endpoint answers a
     1-second TCP probe. These are warnings by default (an offline box may lack
     providers); --strict promotes them to failures.

Drift diagnostics compare the installed state against the repo's canonical copies
in three classes — uninstalled, drifted (content differs), extra (installed with
no canonical source):

  * ~/.claude/agents/colosseum-*.md      vs  agents/colosseum-*.md
  * ~/.claude/skills/colosseum-*/SKILL.md vs skills/colosseum-*/SKILL.md
  * with --project <path>: that project's .colosseum/scripts/opencode_dispatch.py
    and .opencode/agent/*.md against the repo canonical copies.

--live additionally dispatches `opencode run --model <id> "Reply with exactly: ok"`
once per OpenCode profile voice. THIS COSTS MONEY (real provider calls); each call
has its own timeout.

USAGE
    colosseum_doctor.py [--repo <path>] [--project <path>] [--strict]
                        [--live] [--live-timeout 60] [--json]

Exit 0 healthy, 1 drift or failures, 2 tooling error (registry/bom unreadable).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]


def _load_gen(repo: Path):
    """Import gen_roster_docs from the same scripts dir for the shared registry
    loader and profile hash (single source of truth for the hashing algorithm)."""
    path = repo / "scripts" / "gen_roster_docs.py"
    spec = importlib.util.spec_from_file_location("gen_roster_docs", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────────────────────────────────
# Check accumulation
# ─────────────────────────────────────────────────────────────────────────


class Report:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def add(self, category: str, name: str, status: str, detail: str = "") -> None:
        assert status in ("ok", "warn", "fail")
        self.checks.append({"category": category, "name": name,
                            "status": status, "detail": detail})

    def failed(self, strict: bool) -> bool:
        bad = {"fail"} if not strict else {"fail", "warn"}
        return any(c["status"] in bad for c in self.checks)


# ─────────────────────────────────────────────────────────────────────────
# 1. Toolchain vs BOM
# ─────────────────────────────────────────────────────────────────────────

# (tool, version argv, bom key or None, exact-match?) — lean/cargo print a long
# banner so we substring-match their pin.
_TOOLS = [
    ("opencode", ["opencode", "--version"], "opencode", True),
    ("quint", ["quint", "--version"], "quint", True),
    ("uv", ["uv", "--version"], "uv", False),
    ("lean", ["lean", "--version"], "lean", False),
    ("cargo", ["cargo", "--version"], None, False),
]


def _tool_version(argv: list[str]) -> str | None:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (p.stdout + p.stderr).strip().splitlines()[0] if (p.stdout or p.stderr) else ""


def check_toolchain(rep: Report, bom: dict) -> None:
    for tool, argv, key, exact in _TOOLS:
        if shutil.which(tool) is None:
            rep.add("toolchain", tool, "warn", "not on PATH")
            continue
        ver = _tool_version(argv)
        pin = bom["tools"].get(key) if key else None
        if pin is None:
            rep.add("toolchain", tool, "ok", f"present ({ver})")
            continue
        match = (ver == pin) if exact else (pin in (ver or ""))
        rep.add("toolchain", tool, "ok" if match else "fail",
                f"live={ver!r} pin={pin!r}")
    # cargo-kani is optional; check only if present.
    if shutil.which("cargo-kani"):
        ver = _tool_version(["cargo", "kani", "--version"]) or ""
        pin = bom["tools"].get("cargo-kani")
        rep.add("toolchain", "cargo-kani", "ok" if pin and pin in ver else "warn",
                f"live={ver!r} pin={pin!r}")


# ─────────────────────────────────────────────────────────────────────────
# 2. Registry / profile integrity
# ─────────────────────────────────────────────────────────────────────────


def check_registry(rep: Report, gen, reg: dict) -> None:
    for prof in reg["profiles"]:
        want = gen.profile_content_hash(prof)
        stored = prof.get("content_hash")
        rep.add("registry", f"profile {prof['name']} content_hash",
                "ok" if stored == want else "fail",
                f"stored={stored} recomputed={want}")
    # Invariant: canonical-panel voices must carry non-pending calibration.
    for v in reg["voices"]:
        if v["status"] == "canonical-panel":
            ok = v["calibration"] != "pending" and bool(v["calibration"])
            rep.add("registry", f"voice {v['id']} calibration",
                    "ok" if ok else "fail",
                    "canonical-panel requires non-pending calibration"
                    if not ok else "cited")


# ─────────────────────────────────────────────────────────────────────────
# 3. Provider plumbing (free) + optional --live probe
# ─────────────────────────────────────────────────────────────────────────


def _opencode_config_text() -> str:
    cfg = Path.home() / ".config" / "opencode" / "opencode.jsonc"
    return cfg.read_text() if cfg.exists() else ""


def _endpoint_reachable(endpoint: str) -> bool:
    u = urlparse(endpoint)
    host = u.hostname or "127.0.0.1"
    port = u.port or (443 if u.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def profile_opencode_voices(gen, reg: dict, name: str = "canonical-4") -> list[dict]:
    prof = gen.profile_by_name(reg, name)
    return [gen.voice_by_id(reg, pv["id"]) for pv in prof["voices"]
            if gen.voice_by_id(reg, pv["id"])["harness"] == "opencode"]


def check_plumbing(rep: Report, gen, reg: dict) -> None:
    cfg_text = _opencode_config_text()
    have_cfg = bool(cfg_text)
    for v in profile_opencode_voices(gen, reg):
        vid = v["id"]
        if have_cfg:
            named = f'"{v["provider"]}"' in cfg_text or v["provider"] in cfg_text
            rep.add("plumbing", f"{vid}: provider `{v['provider']}` in opencode.jsonc",
                    "ok" if named else "warn",
                    "" if named else "provider not found in ~/.config/opencode/opencode.jsonc")
        else:
            rep.add("plumbing", f"{vid}: opencode.jsonc", "warn",
                    "~/.config/opencode/opencode.jsonc not found")
        for env in v.get("requires_env", []):
            rep.add("plumbing", f"{vid}: ${env}",
                    "ok" if os.environ.get(env) else "warn",
                    "set" if os.environ.get(env) else "unset")
        if v.get("endpoint"):
            up = _endpoint_reachable(v["endpoint"])
            rep.add("plumbing", f"{vid}: endpoint {v['endpoint']}",
                    "ok" if up else "warn", "reachable" if up else "no TCP answer (1s)")


def check_live(rep: Report, gen, reg: dict, timeout: int) -> None:
    if shutil.which("opencode") is None:
        rep.add("live", "opencode", "fail", "opencode not on PATH — cannot probe")
        return
    for v in profile_opencode_voices(gen, reg):
        cmd = ["opencode", "run", "--model", v["model"], "Reply with exactly: ok"]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            ok = p.returncode == 0 and "ok" in (p.stdout or "").lower()
            rep.add("live", f"{v['id']} dispatch", "ok" if ok else "fail",
                    (p.stdout or p.stderr).strip()[:120])
        except subprocess.TimeoutExpired:
            rep.add("live", f"{v['id']} dispatch", "fail", f"timeout after {timeout}s")
        except OSError as e:
            rep.add("live", f"{v['id']} dispatch", "fail", str(e))


# ─────────────────────────────────────────────────────────────────────────
# Drift diagnostics
# ─────────────────────────────────────────────────────────────────────────


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _classify(rep: Report, category: str, name: str,
              canonical: Path | None, installed: Path | None) -> None:
    """Emit one drift check. canonical=None means an installed-only 'extra'."""
    if canonical is not None and (installed is None or not installed.exists()):
        rep.add(category, name, "fail", "uninstalled")
    elif canonical is None:
        rep.add(category, name, "fail", f"extra (no canonical source): {installed}")
    else:
        ch, ih = _sha(canonical), _sha(installed)
        if ch == ih:
            rep.add(category, name, "ok", "in sync")
        else:
            rep.add(category, name, "fail", f"drifted (canonical {ch and ch[:12]} "
                    f"!= installed {ih and ih[:12]})")


def check_home_drift(rep: Report, repo: Path) -> None:
    home = Path.home()
    # Claude Code agents.
    canon_agents = {p.name: p for p in sorted((repo / "agents").glob("colosseum-*.md"))}
    inst_dir = home / ".claude" / "agents"
    for name, canon in canon_agents.items():
        _classify(rep, "drift/agents", f"agents/{name}", canon, inst_dir / name)
    for inst in sorted(inst_dir.glob("colosseum-*.md")) if inst_dir.exists() else []:
        if inst.name not in canon_agents:
            _classify(rep, "drift/agents", f"agents/{inst.name}", None, inst)
    # Skills.
    canon_skills = {p.parent.name: p for p in sorted((repo / "skills").glob("colosseum-*/SKILL.md"))}
    skills_dir = home / ".claude" / "skills"
    for sk, canon in canon_skills.items():
        _classify(rep, "drift/skills", f"skills/{sk}", canon, skills_dir / sk / "SKILL.md")
    if skills_dir.exists():
        for d in sorted(skills_dir.glob("colosseum-*")):
            if d.name not in canon_skills and (d / "SKILL.md").exists():
                _classify(rep, "drift/skills", f"skills/{d.name}", None, d / "SKILL.md")


def check_project_drift(rep: Report, repo: Path, project: Path) -> None:
    project = project.resolve()
    _classify(rep, "drift/project", ".colosseum/scripts/opencode_dispatch.py",
              repo / "scripts" / "opencode_dispatch.py",
              project / ".colosseum" / "scripts" / "opencode_dispatch.py")
    canon_agent_dir = repo / "agents" / "opencode"
    for canon in sorted(canon_agent_dir.glob("*.md")):
        _classify(rep, "drift/project", f".opencode/agent/{canon.name}",
                  canon, project / ".opencode" / "agent" / canon.name)


# ─────────────────────────────────────────────────────────────────────────
# Output
# ─────────────────────────────────────────────────────────────────────────

_ICON = {"ok": "✓", "warn": "!", "fail": "✗"}


def print_human(rep: Report, strict: bool) -> None:
    cat = None
    for c in rep.checks:
        if c["category"] != cat:
            cat = c["category"]
            print(f"\n[{cat}]")
        detail = f"  — {c['detail']}" if c["detail"] else ""
        print(f"  {_ICON[c['status']]} {c['name']}{detail}")
    n_fail = sum(1 for c in rep.checks if c["status"] == "fail")
    n_warn = sum(1 for c in rep.checks if c["status"] == "warn")
    print(f"\n{len(rep.checks)} checks — {n_fail} fail, {n_warn} warn "
          f"({'strict' if strict else 'lenient'})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=REPO)
    ap.add_argument("--project", type=Path, default=None,
                    help="also diff this project's .colosseum/.opencode copies")
    ap.add_argument("--strict", action="store_true",
                    help="promote plumbing/toolchain warnings to failures")
    ap.add_argument("--live", action="store_true",
                    help="dispatch a real 'Reply with exactly: ok' probe per voice (COSTS MONEY)")
    ap.add_argument("--live-timeout", type=int, default=60)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    repo = args.repo.resolve()

    try:
        gen = _load_gen(repo)
        bom = json.loads((repo / "bom.json").read_text())
        reg = gen.load_registry(repo / "registry" / "voices.json")
    except Exception as e:  # noqa: BLE001 — any load failure is a tooling error
        print(f"FATAL (tooling error): {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    rep = Report()
    check_toolchain(rep, bom)
    check_registry(rep, gen, reg)
    check_plumbing(rep, gen, reg)
    check_home_drift(rep, repo)
    if args.project:
        check_project_drift(rep, repo, args.project)
    if args.live:
        print("--live: dispatching real provider probes (this costs money)...",
              file=sys.stderr)
        check_live(rep, gen, reg, args.live_timeout)

    failed = rep.failed(args.strict)
    if args.json:
        print(json.dumps({
            "healthy": not failed,
            "strict": args.strict,
            "bom_tools": bom["tools"],
            "checks": rep.checks,
        }, indent=2))
    else:
        print_human(rep, args.strict)
        print("VERDICT:", "DRIFT/FAIL" if failed else "HEALTHY")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
