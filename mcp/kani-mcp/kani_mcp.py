#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "mcp>=1.2.0",
# ]
# ///
"""
kani-mcp: Wrap cargo-kani (bounded model checker for Rust) as an MCP tool.

Exposes harness discovery, harness execution, and a health check. Output
parsing is best-effort: structured `summary` is provided when stdout is
parseable, but the raw stdout/stderr are always returned for fallback
reasoning by the calling agent.

Run standalone:
    ./kani_mcp.py

Or register with Claude Code via .mcp.json (see README.md).
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

KANI_BIN = os.environ.get("KANI_BIN", "cargo")
DEFAULT_UNWIND = int(os.environ.get("KANI_DEFAULT_UNWIND", "10"))
DEFAULT_TIMEOUT_S = float(os.environ.get("KANI_TIMEOUT_S", "300"))

mcp = FastMCP("kani-mcp")


async def _run(cmd: list[str], cwd: str, timeout: float) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {
            "timed_out": True,
            "returncode": -1,
            "stdout": "",
            "stderr": f"timed out after {timeout}s",
        }
    return {
        "timed_out": False,
        "returncode": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
    }


@mcp.tool()
async def check_kani_health() -> dict[str, Any]:
    """Verify cargo-kani is installed and runnable.

    Returns version output if successful, error detail otherwise. Useful
    as a precondition check before any verification session.
    """
    if not shutil.which(KANI_BIN):
        return {"ok": False, "error": f"`{KANI_BIN}` not found on PATH"}
    result = await _run([KANI_BIN, "kani", "--version"], cwd=".", timeout=30.0)
    return {
        "ok": result["returncode"] == 0,
        "version_output": (result["stdout"] or result["stderr"]).strip(),
        "returncode": result["returncode"],
    }


@mcp.tool()
async def list_kani_harnesses(crate_path: str) -> dict[str, Any]:
    """Discover #[kani::proof] harnesses in a Rust crate.

    Walks the crate's source tree (excluding target/) and reports every
    function annotated with #[kani::proof], including file and line.

    Args:
        crate_path: Absolute path to the crate root (directory containing Cargo.toml).
    """
    root = Path(crate_path)
    if not (root / "Cargo.toml").exists():
        return {"error": f"no Cargo.toml at {crate_path}"}

    harnesses: list[dict[str, Any]] = []
    for rs_file in root.rglob("*.rs"):
        if "target" in rs_file.parts:
            continue
        try:
            lines = rs_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue

        for i, line in enumerate(lines):
            if "#[kani::proof]" in line:
                for j in range(i + 1, min(i + 6, len(lines))):
                    m = re.search(r"\bfn\s+(\w+)", lines[j])
                    if m:
                        harnesses.append(
                            {
                                "name": m.group(1),
                                "file": str(rs_file.relative_to(root)),
                                "line": j + 1,
                            }
                        )
                        break

    return {
        "crate_path": str(root),
        "harnesses": harnesses,
        "count": len(harnesses),
    }


@mcp.tool()
async def run_kani_harness(
    crate_path: str,
    harness_name: str | None = None,
    unwind: int | None = None,
    extra_args: list[str] | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Run cargo-kani against a crate, optionally targeting a specific harness.

    Args:
        crate_path: Absolute path to the crate root (containing Cargo.toml).
        harness_name: If given, runs only this harness. Otherwise runs all harnesses.
        unwind: Loop-unwinding bound for bounded model checking. Default 10.
        extra_args: Additional CLI flags passed verbatim to cargo-kani.
        timeout_s: Override the default per-run timeout.

    Returns:
        dict with `returncode`, `stdout`, `stderr`, `command`, and a parsed
        `summary` when cargo-kani's output is parseable (verdict + per-check status).
    """
    root = Path(crate_path)
    if not (root / "Cargo.toml").exists():
        return {"error": f"no Cargo.toml at {crate_path}"}

    cmd = [KANI_BIN, "kani"]
    if harness_name:
        cmd.extend(["--harness", harness_name])
    cmd.extend(
        ["--default-unwind", str(unwind if unwind is not None else DEFAULT_UNWIND)]
    )
    if extra_args:
        cmd.extend(extra_args)

    result = await _run(cmd, cwd=str(root), timeout=timeout_s or DEFAULT_TIMEOUT_S)
    summary = _parse_kani_summary(result["stdout"])

    return {**result, "command": cmd, "summary": summary}


def _parse_kani_summary(stdout: str) -> dict[str, Any]:
    """Best-effort parse of cargo-kani stdout into structured form.

    cargo-kani's textual output format varies across versions; this parser
    matches common idioms and falls back to raw output otherwise.
    """
    summary: dict[str, Any] = {"verdict": None, "checks": [], "counterexamples": []}

    if re.search(r"VERIFICATION:?-? SUCCESSFUL", stdout):
        summary["verdict"] = "successful"
    elif re.search(r"VERIFICATION:?-? FAILED", stdout):
        summary["verdict"] = "failed"

    for line in stdout.splitlines():
        if "Check " in line and re.search(r":\s*(SUCCESS|FAILURE|UNDETERMINED)", line):
            summary["checks"].append(line.strip())
        if "Failed Checks:" in line:
            summary["counterexamples"].append(line.strip())

    return summary


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
