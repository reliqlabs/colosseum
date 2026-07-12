#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R13 — frontmatter validator green over all skills, agents, wrappers (E6).

Runs scripts/validate_frontmatter.py over the repo (must pass), then
self-tests the validator against known-bad fixtures: an unquoted colon in
the description (the exact defect colosseum-adversarial shipped with), an
over-limit description, a missing permission block on an opencode
wrapper, and a skill whose name does not match its directory. Each must
be caught — a validator that passes everything validates nothing.

Exit 0 pass, 1 fail.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VALIDATOR = REPO / "scripts" / "validate_frontmatter.py"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def run_validator(repo: Path) -> tuple[int, str]:
    proc = subprocess.run(
        ["uv", "run", "--script", str(VALIDATOR), "--repo", str(repo)],
        capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    code, out = run_validator(REPO)
    check("validator green over all real skills, agents, and wrappers",
          code == 0 and "VALIDATOR PASSED" in out, out[-300:])

    with tempfile.TemporaryDirectory(prefix="r13-") as td:
        repo = Path(td)
        (repo / "agents" / "opencode").mkdir(parents=True)

        bad = repo / "skills" / "bad-colon" / "SKILL.md"
        bad.parent.mkdir(parents=True)
        bad.write_text("---\nname: bad-colon\ndescription: dispatches via (`x`: `y`) roster\n---\nbody\n")
        code, out = run_validator(repo)
        check("self-test: unquoted colon in description caught",
              code == 1 and "not valid YAML" in out)

        bad.write_text(f"---\nname: bad-colon\ndescription: \"{'x' * 1300}\"\n---\nbody\n")
        code, out = run_validator(repo)
        check("self-test: over-limit description caught",
              code == 1 and "limit 1024" in out)

        bad.write_text("---\nname: other-name\ndescription: \"fine\"\n---\nbody\n")
        code, out = run_validator(repo)
        check("self-test: skill name/directory mismatch caught",
              code == 1 and "!= directory" in out)
        bad.unlink()

        wrapper = repo / "agents" / "opencode" / "old-agent.md"
        wrapper.write_text("---\ndescription: \"fine\"\nmode: all\ntools:\n  read: true\n---\nbody\n")
        code, out = run_validator(repo)
        check("self-test: opencode wrapper without permission block caught",
              code == 1 and "permission block" in out)
        check("self-test: deprecated tools booleans caught",
              "deprecated tools booleans" in out)

    print()
    if FAILURES:
        print(f"R13: {len(FAILURES)} failure(s)")
        return 1
    print("R13: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
