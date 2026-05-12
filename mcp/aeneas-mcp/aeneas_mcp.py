#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "mcp>=1.2.0",
# ]
# ///
"""
aeneas-mcp: Wrap Aeneas (Rust → Lean 4 extraction) as an MCP tool.

Aeneas translates a functional subset of Rust into Lean 4 (or Coq/F*).
This MCP exposes:

  - health check
  - extraction (`charon` frontend + `aeneas` backend)
  - inventory of extracted Lean definitions

The pipeline is conceptually:

    Rust crate  --charon-->  LLBC  --aeneas-->  Lean 4 .lean files

Recent Aeneas versions bundle both into a single CLI. This wrapper handles
both shapes via configurable binaries.

Run standalone:
    ./aeneas_mcp.py

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

CHARON_BIN = os.environ.get("CHARON_BIN", "charon")
AENEAS_BIN = os.environ.get("AENEAS_BIN", "aeneas")
DEFAULT_TIMEOUT_S = float(os.environ.get("AENEAS_TIMEOUT_S", "600"))
DEFAULT_BACKEND = os.environ.get("AENEAS_BACKEND", "lean")

mcp = FastMCP("aeneas-mcp")


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
async def check_aeneas_health() -> dict[str, Any]:
    """Verify Aeneas (and charon, if separate) are installed and runnable.

    Reports presence and version output for both `charon` and `aeneas` binaries.
    """
    out: dict[str, Any] = {
        "ok": True,
        "charon": {"present": False},
        "aeneas": {"present": False},
    }

    # charon uses subcommand syntax (`charon version`); aeneas takes `--version`.
    probes = (
        ("charon", CHARON_BIN, ["version"]),
        ("aeneas", AENEAS_BIN, ["-version"]),
    )
    for name, binary, version_args in probes:
        if not shutil.which(binary):
            out[name] = {
                "present": False,
                "error": f"`{binary}` not found on PATH",
            }
            out["ok"] = False
            continue
        result = await _run([binary, *version_args], cwd=".", timeout=30.0)
        out[name] = {
            "present": True,
            "version_output": (result["stdout"] or result["stderr"]).strip(),
            "returncode": result["returncode"],
        }
        if result["returncode"] != 0:
            out["ok"] = False

    out["hint"] = (
        "Install Aeneas per https://github.com/AeneasVerif/aeneas — "
        "build charon and aeneas from source and add both to PATH."
    )
    return out


@mcp.tool()
async def run_charon(
    crate_path: str,
    output_path: str | None = None,
    extra_args: list[str] | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Run charon to translate Rust → LLBC.

    Args:
        crate_path: Absolute path to the crate root (Cargo.toml dir).
        output_path: Path where LLBC output is written. Defaults to
                     `<crate_path>/llbc/<crate_name>.llbc` if charon supports it.
        extra_args: Verbatim CLI flags.
        timeout_s: Override the default per-run timeout.
    """
    root = Path(crate_path)
    if not (root / "Cargo.toml").exists():
        return {"error": f"no Cargo.toml at {crate_path}"}

    cmd = [CHARON_BIN, "cargo"]
    if output_path:
        cmd.extend(["--dest-file", output_path])
    if extra_args:
        cmd.extend(extra_args)

    result = await _run(cmd, cwd=str(root), timeout=timeout_s or DEFAULT_TIMEOUT_S)
    return {**result, "command": cmd}


@mcp.tool()
async def extract_rust_to_lean(
    crate_path: str,
    output_dir: str,
    backend: str | None = None,
    extra_charon_args: list[str] | None = None,
    extra_aeneas_args: list[str] | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Run the full Rust → LLBC → Lean extraction pipeline.

    Invokes `charon` to produce LLBC, then `aeneas` to translate that LLBC
    into the chosen backend (default: lean). Writes outputs to `output_dir`.

    Args:
        crate_path: Absolute path to the crate root.
        output_dir: Absolute path where extraction outputs are written.
        backend: Output backend — one of `lean`, `coq`, `fstar`, `hol4`.
        extra_charon_args: Verbatim flags for charon.
        extra_aeneas_args: Verbatim flags for aeneas.
        timeout_s: Override the default per-run timeout (applied to each step).
    """
    root = Path(crate_path)
    if not (root / "Cargo.toml").exists():
        return {"error": f"no Cargo.toml at {crate_path}"}

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chosen_backend = backend or DEFAULT_BACKEND
    if chosen_backend not in ("lean", "coq", "rocq", "fstar", "hol4"):
        return {"error": f"unknown backend: {chosen_backend}"}

    timeout = timeout_s or DEFAULT_TIMEOUT_S
    llbc_path = out_dir / f"{root.name}.llbc"

    # Step 1: charon. Modern Aeneas requires `--preset=aeneas` so charon
    # emits the metadata aeneas expects.
    charon_cmd = [
        CHARON_BIN,
        "cargo",
        "--preset=aeneas",
        "--dest-file",
        str(llbc_path),
    ]
    if extra_charon_args:
        charon_cmd.extend(extra_charon_args)
    charon_result = await _run(charon_cmd, cwd=str(root), timeout=timeout)

    if charon_result["returncode"] != 0:
        return {
            "stage": "charon",
            "ok": False,
            "charon": {**charon_result, "command": charon_cmd},
        }

    # Step 2: aeneas (uses single-dash flags: -backend X -dest DIR)
    aeneas_cmd = [
        AENEAS_BIN,
        str(llbc_path),
        "-backend",
        chosen_backend,
        "-dest",
        str(out_dir),
    ]
    if extra_aeneas_args:
        aeneas_cmd.extend(extra_aeneas_args)
    aeneas_result = await _run(aeneas_cmd, cwd=str(root), timeout=timeout)

    return {
        "stage": "complete" if aeneas_result["returncode"] == 0 else "aeneas",
        "ok": aeneas_result["returncode"] == 0,
        "output_dir": str(out_dir),
        "backend": chosen_backend,
        "llbc_path": str(llbc_path),
        "charon": {**charon_result, "command": charon_cmd},
        "aeneas": {**aeneas_result, "command": aeneas_cmd},
    }


@mcp.tool()
async def list_extracted_definitions(output_dir: str) -> dict[str, Any]:
    """Inventory definitions in an Aeneas-extracted Lean output directory.

    Walks the directory, finds .lean files, and extracts top-level definition
    names (def, theorem, structure, inductive). Useful for navigating what
    Aeneas produced from a Rust crate.

    Args:
        output_dir: Absolute path to the directory containing extracted .lean files.
    """
    root = Path(output_dir)
    if not root.exists():
        return {"error": f"path not found: {output_dir}"}

    defns: list[dict[str, Any]] = []
    decl_re = re.compile(
        r"^\s*(?:@\[[^\]]*\]\s*)?"
        r"(def|theorem|lemma|structure|inductive|class|instance|abbrev)\s+([\w.]+)"
    )
    excluded_dirs = {".lake", "build", ".cache", "lake-packages"}

    for lean_file in root.rglob("*.lean"):
        if any(part in excluded_dirs for part in lean_file.parts):
            continue
        try:
            lines = lean_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines):
            m = decl_re.match(line)
            if m:
                defns.append(
                    {
                        "kind": m.group(1),
                        "name": m.group(2),
                        "file": str(lean_file.relative_to(root)),
                        "line": i + 1,
                    }
                )

    by_kind: dict[str, int] = {}
    for d in defns:
        by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1

    return {
        "output_dir": str(root),
        "definitions": defns,
        "total": len(defns),
        "by_kind": by_kind,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
