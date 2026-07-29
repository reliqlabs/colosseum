#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
colosseum_doctor — offline preflight + drift diagnostics for a Colosseum install (C4).

Offline by default (no model calls, no money spent). It answers three questions:

  1. Is the applicable toolchain present and pinned?  Non-OMP checks compare
     opencode / quint / cargo / lean / uv versions against bom.json. OMP checks
     omit OpenCode because native dispatch does not use it. A present-but-wrong
     version fails; an absent tool warns (a partial install is legitimate).

  2. Is the voice registry self-consistent?  Every profile's content_hash is
     recomputed and compared to the stored value, and the registry invariant is
     enforced: a canonical-panel voice with pending calibration is a failure.

  3. Is the provider plumbing in place, for free?  Non-OMP checks inspect each
     OpenCode voice in the canonical-4 profile: the provider is named in
     ~/.config/opencode/opencode.jsonc, credentials are reachable by one of the
     three paths opencode actually supports (an env var from requires_env, an
     apiKey embedded in the provider's opencode.jsonc options block, or an
     entry in opencode's own auth store at ~/.local/share/opencode/auth.json),
     and any local endpoint answers a 1-second TCP probe. These are warnings by
     default (an offline box may lack providers); --strict promotes them to
     failures.

Drift diagnostics compare the installed state against the repo's canonical copies
in three classes: uninstalled, drifted (content differs), and extra (installed
with no canonical source):

  * ~/.claude/agents/colosseum-*.md      vs  agents/colosseum-*.md
  * ~/.claude/skills/colosseum-*/SKILL.md vs skills/colosseum-*/SKILL.md
  * with --project <path>: that project's .colosseum/scripts/opencode_dispatch.py
    and .opencode/agent/*.md against the repo canonical copies.
  * with an OMP project: `.omp/agents/` against generated OMP wrappers, and
    `.omp/skills/` against the canonical tree with its OMP-only boundary
    rendered into `SKILL.md`.

--live additionally dispatches `opencode run --model <id> "Reply with exactly: ok"`
once per OpenCode profile voice for a non-OMP project. THIS COSTS MONEY (real
provider calls); each call has its own timeout. It is unavailable for OMP projects.

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
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Callable

from colosseum_init import render_omp_skill

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


def check_toolchain(rep: Report, bom: dict, *, include_opencode: bool = True) -> None:
    for tool, argv, key, exact in _TOOLS:
        if tool == "opencode" and not include_opencode:
            continue
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
        omp_model = v.get("omp_model")
        omp_calibration = v.get("omp_calibration")
        if omp_model or omp_calibration:
            ok = (isinstance(omp_model, str) and bool(omp_model)
                  and isinstance(omp_calibration, str) and bool(omp_calibration))
            rep.add("registry", f"voice {v['id']} OMP route",
                    "ok" if ok else "fail",
                    f"model={omp_model!r} calibration={omp_calibration!r}")

    canonical = gen.profile_by_name(reg, "canonical-4")
    missing = [pv["id"] for pv in canonical["voices"]
               if not gen.voice_by_id(reg, pv["id"]).get("omp_model")]
    rep.add("registry", "canonical profile OMP routes",
            "ok" if not missing else "fail",
            "all mapped" if not missing else f"missing={missing}")


# ─────────────────────────────────────────────────────────────────────────
# 3. Provider plumbing (free) + optional --live probe
# ─────────────────────────────────────────────────────────────────────────


def _opencode_config_text() -> str:
    cfg = Path.home() / ".config" / "opencode" / "opencode.jsonc"
    return cfg.read_text() if cfg.exists() else ""


_ENV_PLACEHOLDER_RE = re.compile(r"^\{env:[A-Za-z_][A-Za-z0-9_]*\}$")


def _strip_jsonc_comments(text: str) -> str:
    """Strip // line and /* */ block comments, string-aware so a literal '//'
    inside a quoted value (e.g. a baseURL) survives."""
    out = []
    in_string = False
    escape = False
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


_JSON_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"')


def _strip_trailing_commas(text: str) -> str:
    """Drop a comma that precedes a closing }/] (jsonc allows these; json
    does not), skipping over string literals so a literal ',}' in a value
    survives untouched."""
    out, last = [], 0
    for m in _JSON_STRING_RE.finditer(text):
        out.append(re.sub(r",(\s*[}\]])", r"\1", text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(re.sub(r",(\s*[}\]])", r"\1", text[last:]))
    return "".join(out)


def _opencode_config(cfg_text: str) -> dict | None:
    if not cfg_text:
        return None
    try:
        stripped = _strip_trailing_commas(_strip_jsonc_comments(cfg_text))
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None


def _provider_api_key(cfg: dict | None, provider: str | None) -> str | None:
    """Raw (unresolved) apiKey option string for a provider block, or None if
    the provider or the key is absent."""
    if not cfg or not provider:
        return None
    block = cfg.get("provider", {}).get(provider)
    if not isinstance(block, dict):
        return None
    key = block.get("options", {}).get("apiKey")
    return key if isinstance(key, str) else None


def _auth_store_providers() -> set[str]:
    """Lowercased provider ids present in opencode's auth store. Names only —
    never reads or reports credential values. An absent/unreadable/malformed
    file yields an empty set: that auth source is skipped, not a failure."""
    path = Path.home() / ".local" / "share" / "opencode" / "auth.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return set()
    if not isinstance(data, dict):
        return set()
    return {k.lower() for k in data if isinstance(k, str)}


def _voice_needs_credential(v: dict, cfg: dict | None) -> bool:
    """True if this voice's auth plumbing is worth checking: it declares a
    requires_env, or its provider's config block carries an apiKey option
    (embedded literal or {env:...} placeholder alike). Providers with no
    apiKey option (lmstudio, ds4 — local endpoints) need no credential and
    keep the prior behavior of emitting no check."""
    if v.get("requires_env"):
        return True
    return _provider_api_key(cfg, v.get("provider")) is not None


def _credential_status(v: dict, cfg: dict | None, auth_store: set[str]) -> tuple[str, str]:
    """Check env var, then embedded provider apiKey, then the opencode auth
    store, in that order — the three ways opencode actually authenticates."""
    provider = v.get("provider")
    req_env = v.get("requires_env", [])
    if req_env and all(os.environ.get(e) for e in req_env):
        return "ok", f"via env ({', '.join('$' + e for e in req_env)})"
    raw_key = _provider_api_key(cfg, provider)
    if raw_key and not _ENV_PLACEHOLDER_RE.match(raw_key):
        return "ok", "via provider config (apiKey embedded in opencode.jsonc)"
    if provider and provider.lower() in auth_store:
        return "ok", "via opencode auth store"
    ways = []
    if req_env:
        ways.append(f"set {', '.join('$' + e for e in req_env)}")
    if provider:
        ways.append(f"embed an apiKey for `{provider}` in ~/.config/opencode/opencode.jsonc")
        ways.append(f"run `opencode auth login` for `{provider}`")
    return "warn", "no credential found — " + "; ".join(ways)


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


def check_plumbing(rep: Report, gen, reg: dict, *,
                   include_opencode: bool = True) -> None:
    if not include_opencode:
        return
    cfg_text = _opencode_config_text()
    have_cfg = bool(cfg_text)
    cfg = _opencode_config(cfg_text)
    auth_store = _auth_store_providers()
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
        if _voice_needs_credential(v, cfg):
            status, detail = _credential_status(v, cfg, auth_store)
            rep.add("plumbing", f"{vid}: credentials", status, detail)
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


def _tracked_tree_files(path: Path) -> list[Path]:
    """Files that define a skill tree's identity.

    Python bytecode caches are excluded: importing a skill's helper writes
    `__pycache__` INTO the deployed tree, so hashing it would report drift for
    the ordinary act of running the skill, and would depend on which
    interpreter last touched it.
    """
    return sorted(
        candidate for candidate in path.rglob("*")
        if candidate.is_file()
        and "__pycache__" not in candidate.parts
        and candidate.suffix not in (".pyc", ".pyo")
    )


def _tree_sha(path: Path) -> str | None:
    if not path.is_dir():
        return None
    digest = hashlib.sha256()
    try:
        for candidate in _tracked_tree_files(path):
            digest.update(candidate.relative_to(path).as_posix().encode())
            digest.update(b"\0")
            digest.update(candidate.read_bytes())
            digest.update(b"\0")
    except OSError:
        return None
    return digest.hexdigest()


def _omp_skill_tree_sha(path: Path) -> str | None:
    if not path.is_dir():
        return None
    digest = hashlib.sha256()
    try:
        for candidate in _tracked_tree_files(path):
            relative = candidate.relative_to(path).as_posix()
            content = (render_omp_skill(path).encode()
                       if relative == "SKILL.md" else candidate.read_bytes())
            digest.update(relative.encode())
            digest.update(b"\0")
            digest.update(content)
            digest.update(b"\0")
    except OSError:
        return None
    return digest.hexdigest()



def _classify_tree(rep: Report, category: str, name: str,
                   canonical: Path | None, installed: Path | None,
                   canonical_hash_fn: Callable[[Path], str | None] = _tree_sha) -> None:
    if canonical is not None and (installed is None or not installed.is_dir()):
        rep.add(category, name, "fail", "uninstalled")
    elif canonical is None:
        rep.add(category, name, "fail", f"extra (no canonical source): {installed}")
    else:
        canonical_hash = canonical_hash_fn(canonical)
        installed_hash = _tree_sha(installed)
        if canonical_hash == installed_hash:
            rep.add(category, name, "ok", "in sync")
        else:
            rep.add(category, name, "fail",
                    f"drifted (canonical {canonical_hash and canonical_hash[:12]} "
                    f"!= installed {installed_hash and installed_hash[:12]})")


def check_omp_mcp(rep: Report, repo: Path, project: Path) -> None:
    canonical_path = repo / "templates" / "omp-mcp.json"
    installed_path = project / ".omp" / "mcp.json"
    if not canonical_path.exists():
        rep.add("drift/omp-mcp", ".omp/mcp.json", "fail",
                f"canonical template missing: {canonical_path}")
        return
    if not installed_path.exists():
        rep.add("drift/omp-mcp", ".omp/mcp.json", "fail", "uninstalled")
        return
    try:
        canonical = json.loads(canonical_path.read_text())
        installed = json.loads(installed_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        rep.add("drift/omp-mcp", ".omp/mcp.json", "fail", f"invalid JSON: {exc}")
        return

    if installed.get("$schema") != canonical.get("$schema"):
        rep.add("drift/omp-mcp", ".omp/mcp.json $schema", "fail", "drifted")
    else:
        rep.add("drift/omp-mcp", ".omp/mcp.json $schema", "ok", "in sync")
    installed_servers = installed.get("mcpServers")
    if not isinstance(installed_servers, dict):
        rep.add("drift/omp-mcp", ".omp/mcp.json mcpServers", "fail",
                "missing or not an object")
        return
    for name, expected in canonical["mcpServers"].items():
        actual = installed_servers.get(name)
        rep.add("drift/omp-mcp", f".omp/mcp.json server {name}",
                "ok" if actual == expected else "fail",
                "in sync" if actual == expected else "missing or drifted")


def omp_user_agent_dir() -> Path:
    """OMP's user-level agent dir, resolved the way OMP itself resolves it."""
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


def check_home_drift(rep: Report, repo: Path) -> None:
    """Diff whichever user-level installs actually exist.

    There is no single canonical user-level target: Colosseum installs into
    Claude Code's `~/.claude` OR into OMP's profile-scoped agent dir, and an
    OMP-primary setup deliberately has no Claude install. Asserting one of them
    unconditionally reports a deliberate choice as drift, so each target is
    checked only when it is populated, and a machine with neither gets one
    advisory warning instead of an artifact-by-artifact failure list.
    """
    canon_agents = {p.name: p for p in sorted((repo / "agents").glob("colosseum-*.md"))}
    canon_omp_agents = {p.name: p for p in sorted((repo / "agents" / "omp").glob("*.md"))}
    canon_skills = {p.parent.name: p
                    for p in sorted((repo / "skills").glob("colosseum-*/SKILL.md"))}

    omp_dir = omp_user_agent_dir()
    claude_agents = Path.home() / ".claude" / "agents"
    claude_skills = Path.home() / ".claude" / "skills"
    omp_agents = omp_dir / "agents"
    omp_skills = omp_dir / "skills"

    def populated(agent_dir: Path, skills_dir: Path) -> bool:
        return ((agent_dir.is_dir() and any(agent_dir.glob("colosseum-*.md")))
                or (skills_dir.is_dir() and any(skills_dir.glob("colosseum-*"))))

    installed_any = False

    # Claude Code: generic source, compared file-for-file.
    if populated(claude_agents, claude_skills):
        installed_any = True
        for name, canon in canon_agents.items():
            _classify(rep, "drift/claude-agents", f"agents/{name}",
                      canon, claude_agents / name)
        for inst in sorted(claude_agents.glob("colosseum-*.md")):
            if inst.name not in canon_agents:
                _classify(rep, "drift/claude-agents", f"agents/{inst.name}", None, inst)
        for sk, canon in canon_skills.items():
            _classify(rep, "drift/claude-skills", f"skills/{sk}",
                      canon, claude_skills / sk / "SKILL.md")
        for d in sorted(claude_skills.glob("colosseum-*")):
            if d.name not in canon_skills and (d / "SKILL.md").exists():
                _classify(rep, "drift/claude-skills", f"skills/{d.name}",
                          None, d / "SKILL.md")

    # OMP user level: generated wrappers + boundary-RENDERED skill trees, so the
    # canonical side is hashed through the same renderer the installer used.
    if populated(omp_agents, omp_skills):
        installed_any = True
        for name, canon in canon_omp_agents.items():
            _classify(rep, "drift/omp-user-agents", f"agents/{name}",
                      canon, omp_agents / name)
        for inst in sorted(omp_agents.glob("colosseum-*.md")):
            if inst.name not in canon_omp_agents:
                _classify(rep, "drift/omp-user-agents", f"agents/{inst.name}", None, inst)
        for sk, canon in canon_skills.items():
            _classify_tree(rep, "drift/omp-user-skills", f"skills/{sk}",
                           canon.parent, omp_skills / sk,
                           canonical_hash_fn=_omp_skill_tree_sha)
        for d in sorted(omp_skills.glob("colosseum-*")):
            if d.name not in canon_skills and d.is_dir():
                _classify_tree(rep, "drift/omp-user-skills", f"skills/{d.name}", None, d)

    if not installed_any:
        rep.add("drift/user-install", "colosseum user-level install", "warn",
                f"no Colosseum skills in ~/.claude or {omp_dir}; "
                "install with `colosseum_init.py --user --harness omp`")


def project_harness(project: Path) -> str:
    marker = project.resolve() / ".colosseum" / "harness"
    return marker.read_text().strip() if marker.exists() else "claude-code"


def check_project_drift(rep: Report, repo: Path, project: Path,
                        harness: str | None = None) -> None:
    project = project.resolve()
    harness = harness if harness is not None else project_harness(project)
    for name in ("check_ledger_references.py", "check_evidence_records.py"):
        _classify(rep, "drift/project", f".colosseum/scripts/{name}",
                  repo / "scripts" / name,
                  project / ".colosseum" / "scripts" / name)
    if harness != "omp":
        # The OpenCode transport ships for non-omp harnesses only; an --harness
        # omp scaffold is OMP-native and correctly has no .opencode artifacts.
        _classify(rep, "drift/project", ".colosseum/scripts/opencode_dispatch.py",
                  repo / "scripts" / "opencode_dispatch.py",
                  project / ".colosseum" / "scripts" / "opencode_dispatch.py")
        for canon in sorted((repo / "agents" / "opencode").glob("*.md")):
            _classify(rep, "drift/project", f".opencode/agent/{canon.name}",
                      canon, project / ".opencode" / "agent" / canon.name)

    omp_root = project / ".omp"
    if not omp_root.exists():
        return

    dispatch_path = project / ".colosseum" / "dispatch.json"
    canonical_dispatch = repo / "scripts" / "dispatch.config.example.json"
    try:
        installed_route = json.loads(dispatch_path.read_text()).get("omp_native")
        canonical_route = json.loads(canonical_dispatch.read_text()).get("omp_native")
        ok = installed_route == canonical_route and installed_route is not None
        detail = "in sync" if ok else "missing or drifted"
    except (OSError, json.JSONDecodeError) as exc:
        ok, detail = False, str(exc)
    rep.add("drift/omp-dispatch", ".colosseum/dispatch.json omp_native",
            "ok" if ok else "fail", detail)

    # Project-local skills and agents are OPTIONAL once a user-level OMP
    # install provides them: OMP discovers `~/.omp/agent/{skills,agents}` in
    # every session, so a project that deliberately keeps no local copy is
    # correctly configured, not drifted. Only report a failure when the
    # artifact is absent from BOTH locations. Reporting the deliberate choice
    # as drift is the same harness-blindness that hardcoded ~/.claude.
    user_dir = omp_user_agent_dir()
    user_agents = user_dir / "agents"
    user_skills = user_dir / "skills"

    canonical_agents = {
        path.name: path for path in sorted((repo / "agents" / "omp").glob("*.md"))
    }
    installed_agents = omp_root / "agents"
    for name, canonical in canonical_agents.items():
        local = installed_agents / name
        if not local.exists() and (user_agents / name).exists():
            # Verify the copy that will actually be used. Presence alone is not
            # enough: with --skip-home-drift the drift/omp-user-* checks are
            # suppressed, so an unconditional "ok" here would leave a stale
            # user-level artifact unverified anywhere in the run.
            _classify(rep, "drift/omp-agents", f"user-wide agents/{name}",
                      canonical, user_agents / name)
            continue
        _classify(rep, "drift/omp-agents", f".omp/agents/{name}", canonical, local)
    if installed_agents.exists():
        for installed in sorted(installed_agents.glob("colosseum-*.md")):
            if installed.name not in canonical_agents:
                _classify(rep, "drift/omp-agents",
                          f".omp/agents/{installed.name}", None, installed)

    canonical_skills = {
        path.name: path for path in sorted((repo / "skills").glob("colosseum-*"))
        if (path / "SKILL.md").is_file()
    }
    installed_skills = omp_root / "skills"
    for name, canonical in canonical_skills.items():
        local = installed_skills / name
        if not local.is_dir() and (user_skills / name).is_dir():
            _classify_tree(rep, "drift/omp-skills", f"user-wide skills/{name}",
                           canonical, user_skills / name,
                           canonical_hash_fn=_omp_skill_tree_sha)
            continue
        _classify_tree(rep, "drift/omp-skills", f".omp/skills/{name}",
                       canonical, local,
                       canonical_hash_fn=_omp_skill_tree_sha)
    if installed_skills.exists():
        for installed in sorted(installed_skills.glob("colosseum-*")):
            if installed.name not in canonical_skills and installed.is_dir():
                _classify_tree(rep, "drift/omp-skills",
                               f".omp/skills/{installed.name}", None, installed)
    check_omp_mcp(rep, repo, project)
    # OMP-native deliberation panel artifacts.
    _classify(rep, "drift/omp-panel", ".omp/extensions/colosseum-panel-resolver.ts",
              repo / "templates" / "omp-panel-resolver.ts",
              project / ".omp" / "extensions" / "colosseum-panel-resolver.ts")
    _classify(rep, "drift/omp-panel", ".colosseum/panel-profiles.json",
              repo / "templates" / "omp-panel.json",
              project / ".colosseum" / "panel-profiles.json")


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
                    help="also diff this project's .colosseum/.opencode/.omp copies")
    ap.add_argument("--skip-home-drift", action="store_true",
                    help="skip user-level ~/.claude agent and skill drift checks")
    ap.add_argument("--strict", action="store_true",
                    help="promote plumbing/toolchain warnings to failures")
    ap.add_argument("--live", action="store_true",
                    help="run paid OpenCode probes (non-OMP projects only)")
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

    harness = project_harness(args.project) if args.project else None
    omp_project = harness == "omp"
    if args.live and omp_project:
        ap.error("--live is unavailable for an OMP project; use its native "
                 "agent dispatch instead")

    rep = Report()
    check_toolchain(rep, bom, include_opencode=not omp_project)
    check_registry(rep, gen, reg)
    check_plumbing(rep, gen, reg, include_opencode=not omp_project)
    if not args.skip_home_drift:
        check_home_drift(rep, repo)
    if args.project:
        check_project_drift(rep, repo, args.project, harness=harness)
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
