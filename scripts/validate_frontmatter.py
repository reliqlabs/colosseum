#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6,<7"]
# ///
"""
validate_frontmatter — reference validator for skill and agent frontmatter (E6).

Today's Claude Code loads some malformed frontmatter leniently (unquoted
colons, over-length descriptions); spec-conformant loaders do not. This
validator is the strict contract every skill, agent, and generated wrapper
must pass:

  all files      frontmatter present, strict-YAML parses to a mapping,
                 `description` is a single string of at most 1024 chars
  skills/        `name` present, kebab-case, matches the directory name
  agents/*.md    `name` + `tools` present (Claude Code subagent shape);
                 canonical *-body.md sources are exempt (no frontmatter
                 by design)
  agents/opencode/ `permission` block present, deprecated `tools` absent
                 (the Z1 deny-first contract)
  agents/omp/    `name` present and `tools` is a lowercase OMP tool-id list

USAGE
    validate_frontmatter.py [--repo <path>]

Exit 0 green, 1 failures.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

DESCRIPTION_LIMIT = 1024
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def frontmatter_block(text: str) -> str | None:
    m = re.match(r"^---\n(.*?)\n---(\n|$)", text, re.DOTALL)
    return m.group(1) if m else None


def validate(path: Path, kind: str, failures: list[str]) -> None:
    def fail(msg: str) -> None:
        failures.append(f"{path}: {msg}")

    block = frontmatter_block(path.read_text())
    if block is None:
        fail("no frontmatter block")
        return
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as e:
        fail(f"frontmatter is not valid YAML: {str(e).splitlines()[0]}")
        return
    if not isinstance(data, dict):
        fail(f"frontmatter parses to {type(data).__name__}, not a mapping")
        return

    desc = data.get("description")
    if not isinstance(desc, str):
        fail(f"description missing or not a string (got {type(desc).__name__})")
    elif len(desc) > DESCRIPTION_LIMIT:
        fail(f"description is {len(desc)} chars (limit {DESCRIPTION_LIMIT})")

    if kind == "skill":
        name = data.get("name")
        if not isinstance(name, str) or not NAME_RE.match(name):
            fail(f"skill name missing or not kebab-case: {name!r}")
        elif name != path.parent.name:
            fail(f"skill name {name!r} != directory {path.parent.name!r}")
    elif kind == "claude-agent":
        if not isinstance(data.get("name"), str):
            fail("agent name missing")
        if "tools" not in data:
            fail("agent tools field missing")
    elif kind == "opencode-agent":
        if "permission" not in data or not isinstance(data["permission"], dict):
            fail("opencode agent missing deny-first permission block (Z1)")
        if "tools" in data:
            fail("opencode agent still uses deprecated tools booleans")
    elif kind == "omp-agent":
        if not isinstance(data.get("name"), str):
            fail("OMP agent name missing")
        tools = data.get("tools")
        if not isinstance(tools, list) or not tools or not all(
                isinstance(tool, str) for tool in tools):
            fail("OMP agent tools must be a non-empty string list")
        elif any(not re.match(r"^[a-z][a-z0-9_-]*$", tool) for tool in tools):
            fail("OMP agent tools must use lowercase OMP tool ids")
        if "read-summarize" in data and not isinstance(data["read-summarize"], bool):
            fail("OMP agent read-summarize must be boolean")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    repo = args.repo.resolve()

    failures: list[str] = []
    n = 0
    for path in sorted((repo / "skills").glob("*/SKILL.md")):
        n += 1
        validate(path, "skill", failures)
    for path in sorted((repo / "agents").glob("*.md")):
        if path.name.endswith("-body.md"):
            continue  # canonical bodies carry no frontmatter by design
        n += 1
        validate(path, "claude-agent", failures)
    for path in sorted((repo / "agents" / "opencode").glob("*.md")):
        n += 1
        validate(path, "opencode-agent", failures)
    for path in sorted((repo / "agents" / "omp").glob("*.md")):
        n += 1
        validate(path, "omp-agent", failures)

    print(f"validated {n} file(s)")
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    if failures:
        print(f"\nVALIDATOR FAILED: {len(failures)} failure(s)", file=sys.stderr)
        return 1
    print("VALIDATOR PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
