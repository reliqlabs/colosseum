#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""R14: proof CLI contracts against the locked BOM."""
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
        print(f"  [FAIL] {label}" + (f" ({detail})" if detail else ""))
        FAILURES.append(label)


def help_output(command: str) -> str:
    result = subprocess.run([*command.split(), "--help"], capture_output=True, text=True, timeout=120)
    return result.stdout + result.stderr


def main() -> int:
    if shutil.which("quint") is None:
        print("SKIP-FAIL: quint not on PATH", file=sys.stderr)
        return 2
    for command, flags in BOM["cli_contracts"].items():
        output = help_output(command)
        for flag in flags:
            check(f"`{command}` supports {flag}", flag in output)
    live_quint = subprocess.run(["quint", "--version"], capture_output=True, text=True).stdout.strip()
    quint_pin = BOM["tools"]["quint"]
    check(f"quint version matches BOM pin {quint_pin}", live_quint == quint_pin, f"live={live_quint}")

    if shutil.which("cargo-kani"):
        live = subprocess.run(["cargo", "kani", "--version"], capture_output=True, text=True).stdout.strip()
        pin = BOM["tools"]["cargo-kani"]
        check(f"cargo-kani version matches BOM pin {pin}", pin in live, f"live={live}")
    if shutil.which("lean"):
        result = subprocess.run(["lean", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            live = result.stdout.strip()
            pin = BOM["tools"]["lean"]
            check(f"lean version matches BOM pin {pin}", pin in live, f"live={live}")

    for mcp_script in sorted((REPO / "mcp").glob("*/[a-z]*_mcp.py")):
        head = mcp_script.read_text()[:500]
        if "mcp>=" in head:
            check(f"{mcp_script.relative_to(REPO)}: mcp dep upper-bounded", 'mcp>=1.2.0,<2' in head)
        if "httpx>=" in head:
            check(f"{mcp_script.relative_to(REPO)}: httpx dep upper-bounded", 'httpx>=0.27.0,<1' in head)
    print()
    if FAILURES:
        print(f"R14: {len(FAILURES)} failure(s)")
        return 1
    print("R14: all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
