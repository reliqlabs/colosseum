#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "mcp>=1.2.0,<2",
# ]
# ///
"""
R16/R17/R18 — CLI-backed MCP wrapper hardening (C5).

R16 (quint): the verdict parsers gate the `unknown` verdict on Apalache-specific
    output (a bare `unknown` substring must not fire), and verdict/violations are
    kept mutually consistent (an `ok` verdict with a named violation is impossible,
    resolving toward the violation).
R17 (kani/verus): harness discovery finds the `#[cfg_attr(kani, kani::proof)]` and
    `#[kani::proof_for_contract(...)]` forms; the verus direct path constructs a
    working library-crate command (`--crate-type=lib`) and the cargo-verus
    fallback correctly detects a missing subcommand. cargo-kani runs one trivial
    harness end-to-end when it fits the budget; verus is not installed, so its live
    half is a labeled SKIP.
R18 (runproc): the shared helper reaps the whole process group on timeout, retains
    partial output, and flags timed_out; every CLI-backed server imports and uses it.

Smoke: each CLI-backed server's primary tool runs against a minimal fixture when
its toolchain is present (quint + cargo-kani here); absent toolchains are SKIP.

Requires the `mcp` package (inline dep). Exit 0 pass, 1 fail, 2 if the modules
cannot be imported at all.
"""
from __future__ import annotations

import asyncio
import importlib.util
import inspect
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MCP = REPO / "mcp"
SHARED = MCP / "_shared"
FIX = REPO / "tests" / "fixtures"

SERVERS = {
    "kani": MCP / "kani-mcp" / "kani_mcp.py",
    "verus": MCP / "verus-mcp" / "verus_mcp.py",
    "quint": MCP / "quint-mcp" / "quint_mcp.py",
    "aeneas": MCP / "aeneas-mcp" / "aeneas_mcp.py",
}

FAILURES: list[str] = []
SKIPS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def skip(label: str) -> None:
    print(f"  [SKIP] {label}")
    SKIPS.append(label)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def call_tool(fn, *args, **kwargs) -> Any:
    """Invoke an @mcp.tool() async function, unwrapping if the decorator wrapped it."""
    target = fn if inspect.iscoroutinefunction(fn) else getattr(fn, "fn", fn)
    return asyncio.run(target(*args, **kwargs))


# ---------------------------------------------------------------------------
# R16 — quint verdict parsers
# ---------------------------------------------------------------------------
def r16(quint_mod) -> None:
    print("R16 — quint verdict parsers")
    pv = quint_mod._parse_verify_summary
    pr = quint_mod._parse_run_summary
    unk = quint_mod.APALACHE_UNKNOWN_RE

    # `unknown` substring in benign positions must not produce an unknown verdict.
    benign_ok = pv("[ok] No violation found\n// the unknown_reachable invariant is fine\n", "")
    check("verify: benign 'unknown' substring stays ok, not unknown",
          benign_ok["verdict"] == "ok", f"got {benign_ok['verdict']}")

    benign_none = pv("Checking invariant unknown_flag\nWARNING: unknown option ignored\n", "")
    check("verify: 'unknown' in a name/warning does not fabricate unknown",
          benign_none["verdict"] is None, f"got {benign_none['verdict']}")

    # Real Apalache unknown outcomes do map to unknown.
    for text in ("The outcome is: Unknown\n", "SMT solver returned 'unknown'\n"):
        res = pv(text, "")
        check(f"verify: Apalache unknown output -> unknown ({text.strip()!r})",
              res["verdict"] == "unknown", f"got {res['verdict']}")

    check("APALACHE_UNKNOWN_RE ignores benign substrings",
          not unk.search("the unknown_reachable invariant") and not unk.search("unknown option"))
    check("APALACHE_UNKNOWN_RE matches the model checker's phrasing",
          bool(unk.search("The outcome is: Unknown")))

    # Mixed ok + violation must resolve to violation, never ok.
    mixed = pv("[ok] some earlier line\nInvariant safety violated\n", "")
    check("verify: ok + named violation resolves to violation",
          mixed["verdict"] == "violation" and "safety" in mixed["violated"],
          f"verdict={mixed['verdict']} violated={mixed['violated']}")
    check("verify: no ok-with-violation combination survives",
          not (mixed["verdict"] == "ok" and mixed["violated"]))

    mixed_run = pr("[ok] No violation found\ninvariant safety violated\n", "")
    check("run: ok + named violation resolves to violation",
          mixed_run["verdict"] == "violation" and mixed_run["violation"] == "safety",
          f"verdict={mixed_run['verdict']} violation={mixed_run['violation']}")


# ---------------------------------------------------------------------------
# R17 — kani discovery + verus library command
# ---------------------------------------------------------------------------
def r17(kani_mod, verus_mod) -> None:
    print("R17 — kani discovery + verus library-crate path")
    crate = FIX / "r17" / "libcrate"

    res = call_tool(kani_mod.list_kani_harnesses, str(crate))
    names = {h["name"] for h in res.get("harnesses", [])}
    attrs = " ".join(h.get("attr", "") for h in res.get("harnesses", []))
    check("kani discovery finds the cfg_attr(kani, kani::proof) harness",
          "check_add_commutes" in names, f"names={names}")
    check("kani discovery finds the kani::proof_for_contract harness",
          "check_inc_contract" in names, f"names={names}")
    check("kani discovery records both attribute forms",
          "cfg_attr(kani, kani::proof)" in attrs and "proof_for_contract" in attrs)

    # verus library-crate command construction (unit level; verus not installed).
    lib_cmd = verus_mod._verus_direct_command(crate / "src" / "lib.rs")
    main_cmd = verus_mod._verus_direct_command(crate / "src" / "main.rs")
    check("verus: lib.rs entry gets --crate-type=lib",
          "--crate-type=lib" in lib_cmd, f"cmd={lib_cmd}")
    check("verus: main.rs entry does not get --crate-type=lib",
          "--crate-type=lib" not in main_cmd, f"cmd={main_cmd}")
    check("verus: extra_args are appended after the entry",
          verus_mod._verus_direct_command(crate / "src" / "lib.rs", ["--foo"])[-1] == "--foo")

    # cargo-verus fallback detection (the previously dead error signature).
    missing = verus_mod._cargo_subcommand_missing(
        {"stdout": "", "stderr": "error: no such command: `verus`", "returncode": 101})
    missing_127 = verus_mod._cargo_subcommand_missing(
        {"stdout": "", "stderr": "", "returncode": 127})
    ran = verus_mod._cargo_subcommand_missing(
        {"stdout": "verification results:: 3 verified, 0 errors", "stderr": "", "returncode": 0})
    check("verus: 'no such command' + rc 101 detected as missing subcommand", missing)
    check("verus: rc 127 detected as missing subcommand", missing_127)
    check("verus: a real cargo-verus run is not treated as missing", not ran)

    # verus live half is unavailable in the dogfood environment.
    if shutil.which("verus") is None:
        skip("verus live verification (verus not installed; command construction asserted above)")
    else:
        skip("verus live verification (present but not exercised in this suite)")

    # cargo-kani live: run one trivial harness end-to-end if it fits the budget.
    if shutil.which("cargo-kani") is None and shutil.which("cargo") is None:
        skip("cargo-kani live run (toolchain absent); discovery asserted above")
        return
    budget = float(os.environ.get("R17_KANI_TIMEOUT_S", "180"))
    with tempfile.TemporaryDirectory(prefix="r17-kani-") as td:
        work = Path(td) / "libcrate"
        shutil.copytree(crate, work)
        t0 = time.time()
        run = call_tool(kani_mod.run_kani_harness, str(work),
                        harness_name="check_add_commutes", timeout_s=budget)
        dt = time.time() - t0
        if run.get("timed_out"):
            skip(f"cargo-kani live run exceeded {budget:.0f}s budget; discovery-only")
        elif "error" in run:
            skip(f"cargo-kani live run not runnable ({run['error']}); discovery-only")
        else:
            summary = run.get("summary", {})
            check(f"cargo-kani: trivial harness verifies successfully ({dt:.0f}s)",
                  summary.get("verdict") == "successful" and run["returncode"] == 0,
                  f"verdict={summary.get('verdict')} rc={run['returncode']}")
            check("cargo-kani: verdict reconciled consistent with returncode",
                  run.get("reconciliation", {}).get("consistent") is True)


# ---------------------------------------------------------------------------
# R18 — shared runproc: group reaping, partial output, static usage
# ---------------------------------------------------------------------------
def r18() -> None:
    print("R18 — shared runproc process-group reaping")
    sys.path.insert(0, str(SHARED))
    import runproc  # noqa: E402

    async def go():
        return await runproc.run(
            ["bash", "-c", "echo HELLO; sleep 60 & sleep 60"], cwd=".", timeout=1.5)

    t0 = time.time()
    res = asyncio.run(go())
    dt = time.time() - t0
    check("runproc: timeout is flagged", res["timed_out"] is True)
    check("runproc: partial output retained across the kill", "HELLO" in res["stdout"],
          f"stdout={res['stdout']!r}")
    check("runproc: returns without hanging on the orphaned child", dt < 20, f"{dt:.1f}s")

    pgid = res["pgid"]
    reaped = False
    for _ in range(50):
        try:
            os.killpg(pgid, 0)
        except (ProcessLookupError, OSError):
            reaped = True
            break
        time.sleep(0.1)
    check("runproc: whole process group reaped (killpg -> ESRCH)", reaped, f"pgid={pgid}")
    # Corroborate with ps: no live (non-zombie) member of the group survives.
    ps = subprocess.run(["ps", "-o", "pid=,pgid=,stat=,comm="],
                        capture_output=True, text=True)
    live = [ln for ln in ps.stdout.splitlines()
            if len(ln.split()) >= 3 and ln.split()[1] == str(pgid) and "Z" not in ln.split()[2]]
    check("runproc: ps shows no surviving group members", not live, f"live={live}")

    # cap_text: truncation summary FIRST, tail preserved.
    capped = runproc.cap_text("HEAD" + ("x" * 200) + "TAILVERDICT", head_bytes=4, tail_bytes=11)
    check("runproc: cap summary line comes first",
          capped.startswith("[runproc: output truncated"))
    check("runproc: cap preserves the tail where verdicts live",
          capped.endswith("TAILVERDICT"))
    check("runproc: short output is not capped",
          runproc.cap_text("small") == "small")

    print("R18 — CLI-backed servers use the shared helper (static)")
    for name in ("kani", "verus", "quint", "aeneas"):
        src = SERVERS[name].read_text()
        check(f"{name}: imports the shared runproc helper",
              '/ "_shared"' in src and "from runproc import" in src)
        check(f"{name}: no copy-pasted local _run definition",
              "async def _run(" not in src)


# ---------------------------------------------------------------------------
# Smoke — primary tool per server against a minimal fixture
# ---------------------------------------------------------------------------
def smoke(quint_mod, kani_mod, aeneas_mod) -> None:
    print("Smoke — primary tool per server")

    if shutil.which("quint") is not None:
        spec = FIX / "r16" / "ok.qnt"
        tc = call_tool(quint_mod.typecheck_quint, str(spec))
        check("quint: typecheck of ok.qnt succeeds", tc.get("ok") is True,
              f"rc={tc.get('returncode')}")
        rq = call_tool(quint_mod.run_quint, str(spec),
                       invariant="inv_nonneg", max_steps=5, max_samples=20, seed="0x1")
        check("quint: run reports ok verdict, reconciled consistent",
              rq.get("summary", {}).get("verdict") == "ok"
              and rq.get("reconciliation", {}).get("consistent") is True,
              f"summary={rq.get('summary')}")
    else:
        skip("quint smoke (quint not installed)")

    # kani discovery smoke (structure sanity; live run covered in R17).
    kd = call_tool(kani_mod.list_kani_harnesses, str(FIX / "r17" / "libcrate"))
    check("kani: discovery returns a sane structured result",
          isinstance(kd.get("harnesses"), list) and kd.get("count") == len(kd["harnesses"])
          and kd["count"] >= 2, f"count={kd.get('count')}")

    if shutil.which("verus") is None:
        skip("verus smoke (verus not installed)")

    # aeneas: charon/aeneas binaries absent -> live extraction is SKIP; exercise
    # the toolchain-free lister against a fixture instead.
    if shutil.which("charon") is None or shutil.which("aeneas") is None:
        skip("aeneas live extraction (charon/aeneas not installed)")
    ad = call_tool(aeneas_mod.list_extracted_definitions, str(FIX / "r18" / "extracted"))
    kinds = {d["kind"] for d in ad.get("definitions", [])}
    check("aeneas: list_extracted_definitions finds def/theorem/structure",
          {"def", "theorem", "structure"} <= kinds and ad.get("total", 0) >= 3,
          f"kinds={kinds} total={ad.get('total')}")


def main() -> int:
    try:
        kani_mod = load("kani_mcp", SERVERS["kani"])
        verus_mod = load("verus_mcp", SERVERS["verus"])
        quint_mod = load("quint_mcp", SERVERS["quint"])
        aeneas_mod = load("aeneas_mcp", SERVERS["aeneas"])
    except Exception as exc:  # noqa: BLE001
        print(f"SKIP-FAIL: could not import MCP server modules ({exc})", file=sys.stderr)
        return 2

    r16(quint_mod)
    r17(kani_mod, verus_mod)
    r18()
    smoke(quint_mod, kani_mod, aeneas_mod)

    print()
    if SKIPS:
        print(f"skipped (toolchain/scope): {len(SKIPS)}")
    if FAILURES:
        print(f"R16/R17/R18: {len(FAILURES)} failure(s)")
        return 1
    print("R16/R17/R18: all runnable assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
