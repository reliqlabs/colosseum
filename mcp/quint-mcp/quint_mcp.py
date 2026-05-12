#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "mcp>=1.2.0",
# ]
# ///
"""
quint-mcp: Wrap Quint (Informal Systems' protocol specification language) as
an MCP tool.

Quint sits on the spec-axis of the Colosseum pyramid: it captures protocol
and state-machine properties at the architecture stage, before Rust is
written. This MCP wraps the four most useful Quint operations:

  - typecheck — fast lint of a spec
  - run       — random / symbolic simulation, invariant-checking
  - verify    — Apalache model checking
  - inventory — discover modules, invariants, actions in a spec

Run standalone:
    ./quint_mcp.py

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

QUINT_BIN = os.environ.get("QUINT_BIN", "quint")
DEFAULT_TIMEOUT_S = float(os.environ.get("QUINT_TIMEOUT_S", "600"))
DEFAULT_MAX_STEPS = int(os.environ.get("QUINT_MAX_STEPS", "10"))
DEFAULT_MAX_SAMPLES = int(os.environ.get("QUINT_MAX_SAMPLES", "10000"))

mcp = FastMCP("quint-mcp")


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
async def check_quint_health() -> dict[str, Any]:
    """Verify quint is installed and runnable.

    Reports version and presence of Apalache (required for `verify`).
    """
    if not shutil.which(QUINT_BIN):
        return {
            "ok": False,
            "error": f"`{QUINT_BIN}` not found on PATH",
            "hint": "Install via `npm install -g @informalsystems/quint`",
        }
    result = await _run([QUINT_BIN, "--version"], cwd=".", timeout=30.0)
    out: dict[str, Any] = {
        "ok": result["returncode"] == 0,
        "version_output": (result["stdout"] or result["stderr"]).strip(),
        "returncode": result["returncode"],
    }
    # Apalache is a runtime dependency for `quint verify` — quint downloads it
    # to ~/.quint/apalache on first run, so we don't probe further here.
    out["apalache_hint"] = (
        "`quint verify` will auto-download Apalache to ~/.quint on first use. "
        "Requires JVM 17+. If verify hangs on first call, run it manually once."
    )
    return out


@mcp.tool()
async def list_quint_specs(path: str) -> dict[str, Any]:
    """Inventory modules, invariants, and actions across .qnt files at a path.

    Walks the given path (file or directory) and reports the structural
    surface of each spec: module names, invariant declarations, action names,
    and assume blocks. Useful for orientation before typecheck/run/verify.

    Args:
        path: Absolute path to a .qnt file or directory containing them.
    """
    root = Path(path)
    if not root.exists():
        return {"error": f"path not found: {path}"}

    files: list[Path]
    if root.is_file():
        files = [root] if root.suffix == ".qnt" else []
    else:
        files = list(root.rglob("*.qnt"))

    module_re = re.compile(r"^\s*module\s+(\w+)")
    invariant_re = re.compile(r"^\s*(?:val|def)\s+(\w+)\s*=\s*.*(?:and|or|not|implies|iff|forall|exists|all|any)")
    # Common Quint invariant convention: name starts with `inv_` or ends with `_inv` / `_invariant`
    inv_named_re = re.compile(r"^\s*(?:val|def)\s+((?:inv_|safety_|temporal_)\w+|\w+_(?:inv|invariant|safety|live))\s*[=:]")
    action_re = re.compile(r"^\s*action\s+(\w+)")
    assume_re = re.compile(r"^\s*assume\s+(\w+)")

    findings: list[dict[str, Any]] = []
    for qnt_file in files:
        try:
            lines = qnt_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        modules: list[dict[str, Any]] = []
        invariants: list[dict[str, Any]] = []
        actions: list[dict[str, Any]] = []
        assumes: list[dict[str, Any]] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(("//", "/*", "*")):
                continue
            m = module_re.match(line)
            if m:
                modules.append({"name": m.group(1), "line": i + 1})
                continue
            m = inv_named_re.match(line)
            if m:
                invariants.append({"name": m.group(1), "line": i + 1})
                continue
            m = action_re.match(line)
            if m:
                actions.append({"name": m.group(1), "line": i + 1})
                continue
            m = assume_re.match(line)
            if m:
                assumes.append({"name": m.group(1), "line": i + 1})
        findings.append(
            {
                "file": str(qnt_file),
                "modules": modules,
                "invariants": invariants,
                "actions": actions,
                "assumes": assumes,
            }
        )

    totals = {
        "files": len(findings),
        "modules": sum(len(f["modules"]) for f in findings),
        "invariants": sum(len(f["invariants"]) for f in findings),
        "actions": sum(len(f["actions"]) for f in findings),
        "assumes": sum(len(f["assumes"]) for f in findings),
    }
    return {"path": str(root), "files": findings, "totals": totals}


@mcp.tool()
async def typecheck_quint(
    spec_path: str,
    extra_args: list[str] | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Typecheck a Quint specification.

    Fastest validation pass — catches syntax and type errors without
    running the spec or invoking Apalache.

    Args:
        spec_path: Absolute path to the .qnt file.
        extra_args: Verbatim flags appended to `quint typecheck`.
        timeout_s: Override the default timeout.
    """
    p = Path(spec_path)
    if not p.exists():
        return {"error": f"file not found: {spec_path}"}
    if p.suffix != ".qnt":
        return {"error": f"expected .qnt file, got: {spec_path}"}

    cmd = [QUINT_BIN, "typecheck", str(p)]
    if extra_args:
        cmd.extend(extra_args)
    result = await _run(cmd, cwd=str(p.parent), timeout=timeout_s or DEFAULT_TIMEOUT_S)
    return {**result, "command": cmd, "ok": result["returncode"] == 0}


@mcp.tool()
async def run_quint(
    spec_path: str,
    invariant: str | None = None,
    main: str | None = None,
    max_steps: int | None = None,
    max_samples: int | None = None,
    seed: str | None = None,
    extra_args: list[str] | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Simulate a Quint specification via random execution; optionally check
    an invariant.

    `run` is the cheap-fast layer — it explores traces randomly, looking for
    invariant violations. Use it for quick reality checks before bringing
    Apalache (`verify`) to bear.

    Args:
        spec_path: Absolute path to the .qnt file.
        invariant: Name of invariant(s) to check (comma-separated). If omitted,
                   simulation runs but no invariant is checked.
        main: Main module name. Defaults to the filename stem.
        max_steps: Max steps per trace. Default 10.
        max_samples: Max independent traces to sample. Default 10000.
        seed: Random seed for reproducibility.
        extra_args: Verbatim flags appended to `quint run`.
        timeout_s: Override the default timeout.
    """
    p = Path(spec_path)
    if not p.exists():
        return {"error": f"file not found: {spec_path}"}
    if p.suffix != ".qnt":
        return {"error": f"expected .qnt file, got: {spec_path}"}

    cmd = [
        QUINT_BIN,
        "run",
        str(p),
        "--max-steps",
        str(max_steps if max_steps is not None else DEFAULT_MAX_STEPS),
        "--max-samples",
        str(max_samples if max_samples is not None else DEFAULT_MAX_SAMPLES),
    ]
    if invariant:
        cmd.extend(["--invariant", invariant])
    if main:
        cmd.extend(["--main", main])
    if seed:
        cmd.extend(["--seed", seed])
    if extra_args:
        cmd.extend(extra_args)

    result = await _run(cmd, cwd=str(p.parent), timeout=timeout_s or DEFAULT_TIMEOUT_S)
    summary = _parse_run_summary(result["stdout"], result["stderr"])
    return {**result, "command": cmd, "summary": summary}


@mcp.tool()
async def verify_quint(
    spec_path: str,
    invariant: str | None = None,
    invariants: list[str] | None = None,
    inductive_invariant: str | None = None,
    main: str | None = None,
    max_steps: int | None = None,
    extra_args: list[str] | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """Verify a Quint specification via Apalache (symbolic model checking).

    `verify` is the expensive-strong layer — it exhaustively checks invariants
    up to `max_steps` symbolic depth. Slower than `run` but produces real
    proofs (up to the bound), not statistical confidence.

    Args:
        spec_path: Absolute path to the .qnt file.
        invariant: Single or comma-separated invariant names.
        invariants: List of invariant names; checked as conjunction with
                    per-invariant violation reporting.
        inductive_invariant: Name of an inductive invariant (proven without
                             a step bound).
        main: Main module. Defaults to filename stem.
        max_steps: Symbolic depth. Default 10.
        extra_args: Verbatim flags appended to `quint verify`.
        timeout_s: Override the default timeout. Apalache runs can be long.
    """
    p = Path(spec_path)
    if not p.exists():
        return {"error": f"file not found: {spec_path}"}
    if p.suffix != ".qnt":
        return {"error": f"expected .qnt file, got: {spec_path}"}

    cmd = [QUINT_BIN, "verify", str(p)]
    if invariant:
        cmd.extend(["--invariant", invariant])
    if invariants:
        cmd.extend(["--invariants", *invariants])
    if inductive_invariant:
        cmd.extend(["--inductive-invariant", inductive_invariant])
    if main:
        cmd.extend(["--main", main])
    if max_steps is not None:
        cmd.extend(["--max-steps", str(max_steps)])
    if extra_args:
        cmd.extend(extra_args)

    result = await _run(cmd, cwd=str(p.parent), timeout=timeout_s or DEFAULT_TIMEOUT_S)
    summary = _parse_verify_summary(result["stdout"], result["stderr"])
    return {**result, "command": cmd, "summary": summary}


def _parse_run_summary(stdout: str, stderr: str) -> dict[str, Any]:
    text = stdout + "\n" + stderr
    summary: dict[str, Any] = {"verdict": None, "samples": None, "steps": None, "violation": None}
    if re.search(r"\[ok\]", text) or re.search(r"All sampled traces satisfied", text, re.IGNORECASE):
        summary["verdict"] = "ok"
    elif re.search(r"\[violation\]", text, re.IGNORECASE) or "violation" in text.lower():
        summary["verdict"] = "violation"
        m = re.search(r"invariant\s+(\w+)\s+(?:is\s+)?violated", text, re.IGNORECASE)
        if m:
            summary["violation"] = m.group(1)
    m = re.search(r"(\d+)\s+samples?", text)
    if m:
        summary["samples"] = int(m.group(1))
    m = re.search(r"(\d+)\s+steps?", text)
    if m:
        summary["steps"] = int(m.group(1))
    return summary


def _parse_verify_summary(stdout: str, stderr: str) -> dict[str, Any]:
    text = stdout + "\n" + stderr
    summary: dict[str, Any] = {"verdict": None, "violated": [], "counterexample_file": None}
    if re.search(r"\[ok\]", text) or re.search(r"No violation", text, re.IGNORECASE):
        summary["verdict"] = "ok"
    elif re.search(r"\[violation\]", text, re.IGNORECASE):
        summary["verdict"] = "violation"
    elif re.search(r"unknown", text, re.IGNORECASE):
        summary["verdict"] = "unknown"

    for m in re.finditer(r"(?:Invariant|invariant)\s+(\w+)\s+(?:is\s+)?violated", text):
        summary["violated"].append(m.group(1))

    m = re.search(r"counterexample.*?(\S+\.itf\.json)", text, re.IGNORECASE)
    if m:
        summary["counterexample_file"] = m.group(1)

    return summary


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
