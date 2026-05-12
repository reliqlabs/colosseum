#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "mcp>=1.2.0",
# ]
# ///
"""
verus-mcp: Wrap Verus (SMT-backed verification for Rust) as an MCP tool.

Verus sits above Kani on the Colosseum verification pyramid: SMT-based,
faster than full theorem proving but more expressive than bounded model
checking. Annotations (`requires`, `ensures`, `invariant`, `spec`) are
discharged by Z3.

Exposes annotation discovery, file/crate verification, and a health check.
Output parsing is best-effort; raw stdout/stderr are always returned for
fallback reasoning.

Run standalone:
    ./verus_mcp.py

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

VERUS_BIN = os.environ.get("VERUS_BIN", "verus")
DEFAULT_TIMEOUT_S = float(os.environ.get("VERUS_TIMEOUT_S", "300"))

mcp = FastMCP("verus-mcp")

# Verus annotation/keyword markers used for discovery
VERUS_MARKERS = (
    "verus!",
    "#[verifier",
    "spec fn",
    "proof fn",
    "exec fn",
    "requires",
    "ensures",
    "invariant",
    "decreases",
)


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
async def check_verus_health() -> dict[str, Any]:
    """Verify Verus is installed and runnable.

    Returns version output if successful, error detail otherwise.
    """
    if not shutil.which(VERUS_BIN):
        return {
            "ok": False,
            "error": f"`{VERUS_BIN}` not found on PATH",
            "hint": "Install Verus per https://verus-lang.github.io/verus/guide/install.html",
        }
    result = await _run([VERUS_BIN, "--version"], cwd=".", timeout=30.0)
    return {
        "ok": result["returncode"] == 0,
        "version_output": (result["stdout"] or result["stderr"]).strip(),
        "returncode": result["returncode"],
    }


@mcp.tool()
async def list_verus_annotations(path: str) -> dict[str, Any]:
    """Inventory Verus annotations in a file or directory.

    Walks the given path (file or directory tree) and reports occurrences
    of common Verus markers: `spec fn`, `proof fn`, `requires`, `ensures`,
    `invariant`, `verus!` blocks, `#[verifier(...)]` attributes.

    Args:
        path: Absolute path to a Rust source file or a directory.
    """
    root = Path(path)
    if not root.exists():
        return {"error": f"path not found: {path}"}

    files: list[Path]
    if root.is_file():
        files = [root]
    else:
        files = [p for p in root.rglob("*.rs") if "target" not in p.parts]

    findings: list[dict[str, Any]] = []
    for rs_file in files:
        try:
            lines = rs_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(("//", "///", "/*", "*")):
                continue
            for marker in VERUS_MARKERS:
                if marker in stripped:
                    findings.append(
                        {
                            "marker": marker,
                            "file": str(rs_file),
                            "line": i + 1,
                            "text": stripped[:200],
                        }
                    )
                    break

    return {"path": str(root), "findings": findings, "count": len(findings)}


@mcp.tool()
async def verify_verus_file(
    file_path: str,
    extra_args: list[str] | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Run Verus against a single Rust source file.

    Args:
        file_path: Absolute path to the .rs file to verify.
        extra_args: Verbatim CLI flags appended after the file path.
        timeout_s: Override the default per-run timeout.

    Returns:
        dict with `returncode`, `stdout`, `stderr`, `command`, and a parsed
        `summary` (verdict, verified/error counts, error locations).
    """
    p = Path(file_path)
    if not p.exists():
        return {"error": f"file not found: {file_path}"}
    if p.suffix != ".rs":
        return {"error": f"expected .rs file, got: {file_path}"}

    cmd = [VERUS_BIN, str(p)]
    if extra_args:
        cmd.extend(extra_args)

    result = await _run(
        cmd, cwd=str(p.parent), timeout=timeout_s or DEFAULT_TIMEOUT_S
    )
    summary = _parse_verus_summary(result["stdout"] + "\n" + result["stderr"])

    return {**result, "command": cmd, "summary": summary}


@mcp.tool()
async def verify_verus_crate(
    crate_path: str,
    extra_args: list[str] | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Run Verus against a Rust crate (uses Verus's cargo integration if available).

    Falls back to file-by-file verification if cargo-verus is not available.

    Args:
        crate_path: Absolute path to the crate root (Cargo.toml dir).
        extra_args: Verbatim CLI flags.
        timeout_s: Override the default per-run timeout.
    """
    root = Path(crate_path)
    if not (root / "Cargo.toml").exists():
        return {"error": f"no Cargo.toml at {crate_path}"}

    # Prefer `cargo verus` if available, else fall back to invoking verus on src/lib.rs
    cargo = shutil.which("cargo")
    if cargo:
        cmd = [cargo, "verus"]
        if extra_args:
            cmd.extend(extra_args)
        result = await _run(
            cmd, cwd=str(root), timeout=timeout_s or DEFAULT_TIMEOUT_S
        )
        if result["returncode"] != 127 and "no such subcommand" not in result["stderr"].lower():
            summary = _parse_verus_summary(result["stdout"] + "\n" + result["stderr"])
            return {**result, "command": cmd, "summary": summary, "mode": "cargo-verus"}

    # Fall back: invoke verus on src/lib.rs or src/main.rs
    entry: Path | None = None
    for candidate in ("src/lib.rs", "src/main.rs"):
        if (root / candidate).exists():
            entry = root / candidate
            break
    if entry is None:
        return {"error": f"no src/lib.rs or src/main.rs in {crate_path}"}

    cmd = [VERUS_BIN, str(entry)]
    if extra_args:
        cmd.extend(extra_args)
    result = await _run(
        cmd, cwd=str(root), timeout=timeout_s or DEFAULT_TIMEOUT_S
    )
    summary = _parse_verus_summary(result["stdout"] + "\n" + result["stderr"])
    return {**result, "command": cmd, "summary": summary, "mode": "verus-direct"}


def _parse_verus_summary(text: str) -> dict[str, Any]:
    """Best-effort parse of Verus output into structured form.

    Looks for `verification results:: N verified, M errors` and per-error
    `file.rs:line:col:` markers.
    """
    summary: dict[str, Any] = {
        "verdict": None,
        "verified": None,
        "errors": None,
        "error_locations": [],
    }

    m = re.search(
        r"verification results::?\s*(\d+)\s+verified,?\s*(\d+)\s+errors?",
        text,
        re.IGNORECASE,
    )
    if m:
        summary["verified"] = int(m.group(1))
        summary["errors"] = int(m.group(2))
        summary["verdict"] = "successful" if summary["errors"] == 0 else "failed"

    for line in text.splitlines():
        loc = re.match(r"^(.+\.rs):(\d+):(\d+):\s*(.*)$", line.strip())
        if loc:
            summary["error_locations"].append(
                {
                    "file": loc.group(1),
                    "line": int(loc.group(2)),
                    "col": int(loc.group(3)),
                    "message": loc.group(4)[:200],
                }
            )

    return summary


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
