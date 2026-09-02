#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""R13: static OMP frontmatter validator and known-bad fixtures."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VALIDATOR = REPO / "scripts" / "validate_frontmatter.py"
FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  [ok]   {label}")
    else:
        print(f"  [FAIL] {label}" + (f" ({detail})" if detail else ""))
        FAILURES.append(label)


def run_validator(repo: Path) -> tuple[int, str]:
    result = subprocess.run(
        ["uv", "run", "--script", str(VALIDATOR), "--repo", str(repo)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode, result.stdout + result.stderr


def main() -> int:
    code, output = run_validator(REPO)
    check("real package frontmatter passes", code == 0 and "VALIDATOR PASSED" in output, output[-300:])
    with tempfile.TemporaryDirectory(prefix="r13-") as temporary:
        repo = Path(temporary)
        agents = repo / "agents"
        skills = repo / "skills"
        agents.mkdir()

        bad_skill = skills / "bad-colon" / "SKILL.md"
        bad_skill.parent.mkdir(parents=True)
        bad_skill.write_text("---\nname: bad-colon\ndescription: dispatch (`x`: `y`)\n---\nbody\n")
        code, output = run_validator(repo)
        check("unquoted colon rejected", code == 1 and "not valid YAML" in output)
        bad_skill.write_text(f"---\nname: bad-colon\ndescription: \"{'x' * 1300}\"\n---\nbody\n")
        code, output = run_validator(repo)
        check("over-limit description rejected", code == 1 and "limit 1024" in output)
        bad_skill.write_text("---\nname: wrong-name\ndescription: fine\n---\nbody\n")
        code, output = run_validator(repo)
        check("skill directory mismatch rejected", code == 1 and "!= directory" in output)
        bad_skill.unlink()

        agent = agents / "bad-agent.md"
        agent.write_text("---\nname: wrong-agent\ndescription: fine\ntools: [Read]\nrestrictTools: \"yes\"\n---\nbody\n")
        code, output = run_validator(repo)
        check("agent filename mismatch rejected", code == 1 and "!= filename" in output)
        check("uppercase tool rejected", "lowercase OMP tool ids" in output)
        check("non-boolean restrictTools rejected", "restrictTools must be boolean" in output)

    print()
    if FAILURES:
        print(f"R13: {len(FAILURES)} failure(s)")
        return 1
    print("R13: all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
