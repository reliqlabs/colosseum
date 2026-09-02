#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6,<7"]
# ///
"""Validate FV skill and static OMP agent frontmatter."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

DESCRIPTION_LIMIT = 1024
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TOOL_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
THINKING_LEVELS = {"off", "minimal", "low", "medium", "high", "xhigh", "max", "auto"}


def frontmatter_block(text: str) -> str | None:
    match = re.match(r"^---\n(.*?)\n---(\n|$)", text, re.DOTALL)
    return match.group(1) if match else None


def field(data: dict, canonical: str, alias: str):
    if canonical in data and alias in data:
        return None, f"both {canonical!r} and {alias!r} are present"
    return data.get(canonical, data.get(alias)), None


def validate(path: Path, kind: str, failures: list[str]) -> None:
    def fail(message: str) -> None:
        failures.append(f"{path}: {message}")

    block = frontmatter_block(path.read_text())
    if block is None:
        fail("no frontmatter block")
        return
    try:
        data = yaml.safe_load(block)
    except yaml.YAMLError as error:
        fail(f"frontmatter is not valid YAML: {str(error).splitlines()[0]}")
        return
    if not isinstance(data, dict):
        fail(f"frontmatter parses to {type(data).__name__}, not a mapping")
        return

    description = data.get("description")
    if not isinstance(description, str):
        fail(f"description missing or not a string (got {type(description).__name__})")
    elif len(description) > DESCRIPTION_LIMIT:
        fail(f"description is {len(description)} chars (limit {DESCRIPTION_LIMIT})")

    name = data.get("name")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        fail(f"name missing or not kebab-case: {name!r}")
    elif kind == "skill" and name != path.parent.name:
        fail(f"skill name {name!r} != directory {path.parent.name!r}")

    if kind != "agent":
        return
    if name != path.stem:
        fail(f"agent name {name!r} != filename {path.stem!r}")
    tools = data.get("tools")
    if not isinstance(tools, list) or not tools or not all(isinstance(tool, str) for tool in tools):
        fail("agent tools must be a non-empty string list")
    elif any(not TOOL_RE.fullmatch(tool) for tool in tools):
        fail("agent tools must use lowercase OMP tool ids")

    restrict_tools = data.get("restrictTools")
    if restrict_tools is not None and not isinstance(restrict_tools, bool):
        fail("restrictTools must be boolean")
    thinking, thinking_error = field(data, "thinkingLevel", "thinking-level")
    if thinking_error:
        fail(thinking_error)
    elif thinking is not None and thinking not in THINKING_LEVELS:
        fail(f"thinkingLevel is invalid: {thinking!r}")
    read_summarize, summarize_error = field(data, "readSummarize", "read-summarize")
    if summarize_error:
        fail(summarize_error)
    elif read_summarize is not None and not isinstance(read_summarize, bool):
        fail("readSummarize must be boolean")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    repo = args.repo.resolve()
    failures: list[str] = []
    count = 0
    for path in sorted((repo / "skills").glob("*/SKILL.md")):
        count += 1
        validate(path, "skill", failures)
    for path in sorted((repo / "agents").glob("*.md")):
        count += 1
        validate(path, "agent", failures)
    print(f"validated {count} file(s)")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"\nVALIDATOR FAILED: {len(failures)} failure(s)")
        return 1
    print("VALIDATOR PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
