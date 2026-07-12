#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6,<7"]
# ///
"""
R11 (static half) — deny-first agent permission profiles (Z1, contract G5).

Parses the generated OpenCode agent wrappers and asserts the permission
frontmatter is deny-first: reviewer has no shell/write/network/subagent
access, generator shell is scoped to the quint CLI, secrets are masked for
both, and the obligation manifest is not generator-writable. Also asserts
the phantom `--dangerously-skip-permissions` flag (silently ignored by
OpenCode 1.x) no longer appears in dispatch code or skills, and that dist
files match the build (no drift).

The live half of R11 (dispatch a probe agent that attempts
shell/write/network/manifest-write and observe denials) lands with Z2,
which provides the ephemeral worktree the probe runs in.

Exit 0 on pass, 1 on failure. One line per assertion.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def frontmatter(path: Path) -> dict:
    text = path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: no frontmatter")
    end = text.index("\n---", 4)
    return yaml.safe_load(text[4:end])


def main() -> int:
    reviewer_path = REPO / "agents/opencode/spec-adversary.md"
    generator_path = REPO / "agents/opencode/quint-spec-generator.md"

    # --- dist files exist and match the build (no drift) ---
    lint = subprocess.run(
        [str(REPO / "scripts/install-agents.py"), "lint"],
        capture_output=True, text=True,
    )
    check("install-agents lint: dist matches canonical build", lint.returncode == 0,
          lint.stderr.strip().splitlines()[-1] if lint.stderr.strip() else "")

    reviewer = frontmatter(reviewer_path)
    generator = frontmatter(generator_path)

    for name, fm in (("spec-adversary", reviewer), ("quint-spec-generator", generator)):
        check(f"{name}: uses permission block, not deprecated tools booleans",
              "permission" in fm and "tools" not in fm)

    rp = reviewer.get("permission", {})
    gp = generator.get("permission", {})

    # --- reviewer (spec-adversary): read-only, no shell/write/network/subagents ---
    for tool in ("edit", "bash", "task", "skill", "webfetch", "websearch",
                 "external_directory"):
        check(f"spec-adversary: {tool} denied", rp.get(tool) == "deny",
              f"got {rp.get(tool)!r}")
    for pattern in ("**/.env", "**/.env.*", "**/*.secret", "**/secrets.*", "**/id_rsa*"):
        check(f"spec-adversary: read {pattern} denied",
              isinstance(rp.get("read"), dict) and rp["read"].get(pattern) == "deny")
    check("spec-adversary: read otherwise allowed",
          isinstance(rp.get("read"), dict) and rp["read"].get("*") == "allow")

    # --- generator (quint-spec-generator): shell scoped to quint, manifest not writable ---
    check("quint-spec-generator: bash default denied",
          isinstance(gp.get("bash"), dict) and gp["bash"].get("*") == "deny",
          f"got {gp.get('bash')!r}")
    check("quint-spec-generator: bash quint CLI allowed",
          isinstance(gp.get("bash"), dict) and gp["bash"].get("quint *") == "allow")
    check("quint-spec-generator: bash has no other allow rules",
          isinstance(gp.get("bash"), dict)
          and {k for k, v in gp["bash"].items() if v == "allow"} == {"quint *"})
    for pattern in ("**/.colosseum/obligations*", "**/intent.md", "**/.env", "**/.env.*"):
        check(f"quint-spec-generator: edit {pattern} denied",
              isinstance(gp.get("edit"), dict) and gp["edit"].get(pattern) == "deny")
    for tool in ("task", "skill", "webfetch", "websearch", "external_directory"):
        check(f"quint-spec-generator: {tool} denied", gp.get(tool) == "deny",
              f"got {gp.get(tool)!r}")
    for pattern in ("**/.env", "**/.env.*", "**/*.secret", "**/secrets.*"):
        check(f"quint-spec-generator: read {pattern} denied",
              isinstance(gp.get("read"), dict) and gp["read"].get(pattern) == "deny")

    # --- phantom flag gone from dispatch code and skills ---
    flag = "--dangerously-skip-permissions"
    hits = []
    for sub in ("scripts", "skills", "agents"):
        for path in sorted((REPO / sub).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".md", ".json"}:
                text = path.read_text(errors="replace")
                # allow prose explaining the flag doesn't exist; forbid it in command lines
                for line in text.splitlines():
                    if flag in line and ("opencode run" in line or line.strip().startswith('"--')):
                        hits.append(f"{path.relative_to(REPO)}: {line.strip()}")
    check(f"no invocation passes {flag}", not hits, "; ".join(hits))

    print()
    if FAILURES:
        print(f"R11 static: {len(FAILURES)} failure(s)")
        return 1
    print("R11 static: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
