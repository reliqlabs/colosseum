#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R14 — CLI contract snapshots against the locked BOM (E6).

The pipeline shells out to opencode and quint with specific flags; a flag
that disappears (or never existed, like --dangerously-skip-permissions)
must fail here rather than in a field run. This test asserts every flag
named in bom.json's cli_contracts exists in the live `--help` output, and
that live tool versions match the BOM pins (bump the pin deliberately
when upgrading, then re-run the suite).

Exit 0 pass, 1 fail, 2 if a pinned tool is not installed.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOM = json.loads((REPO / "bom.json").read_text())
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def help_output(command: str) -> str:
    proc = subprocess.run([*command.split(), "--help"],
                          capture_output=True, text=True, timeout=120)
    return proc.stdout + proc.stderr


def main() -> int:
    for tool in ("opencode", "quint"):
        if shutil.which(tool) is None:
            print(f"SKIP-FAIL: {tool} not on PATH", file=sys.stderr)
            return 2

    # Flag contracts.
    for command, flags in BOM["cli_contracts"].items():
        out = help_output(command)
        for flag in flags:
            check(f"`{command}` supports {flag}", flag in out)

    # The phantom-flag class: nothing the pipeline passes may be absent, and
    # the one historic phantom stays absent.
    out = help_output("opencode run")
    check("phantom --dangerously-skip-permissions is (still) not a real flag",
          "--dangerously-skip-permissions" not in out)

    # Version pins.
    live = {
        "opencode": subprocess.run(["opencode", "--version"], capture_output=True,
                                   text=True).stdout.strip(),
        "quint": subprocess.run(["quint", "--version"], capture_output=True,
                                text=True).stdout.strip(),
    }
    for tool in ("opencode", "quint"):
        pin = BOM["tools"][tool]
        check(f"{tool} version matches BOM pin {pin} (bump bom.json deliberately)",
              live[tool] == pin, f"live={live[tool]}")

    if shutil.which("cargo-kani"):
        kani = subprocess.run(["cargo", "kani", "--version"], capture_output=True,
                              text=True).stdout.strip()
        pin = BOM["tools"]["cargo-kani"]
        check(f"cargo-kani version matches BOM pin {pin}", pin in kani,
              f"live={kani}")
    if shutil.which("lean"):
        lean = subprocess.run(["lean", "--version"], capture_output=True,
                              text=True).stdout.strip()
        pin = BOM["tools"]["lean"]
        check(f"lean version matches BOM pin {pin}", pin in lean, f"live={lean}")

    # Inline Python deps carry upper bounds (locked BOM, not open-ended).
    for mcp_script in sorted((REPO / "mcp").glob("*/[a-z]*_mcp.py")):
        head = mcp_script.read_text()[:500]
        if "mcp>=" in head:
            check(f"{mcp_script.relative_to(REPO)}: mcp dep upper-bounded",
                  'mcp>=1.2.0,<2' in head)
        if "httpx>=" in head:
            check(f"{mcp_script.relative_to(REPO)}: httpx dep upper-bounded",
                  'httpx>=0.27.0,<1' in head)

    print()
    if FAILURES:
        print(f"R14: {len(FAILURES)} failure(s)")
        return 1
    print("R14: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
