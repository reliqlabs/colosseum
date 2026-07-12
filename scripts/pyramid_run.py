#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
pyramid_run — headless runner for the deterministic pyramid layers (E4, G2).

Runs the layers that need no agent (types, lints, property tests, fuzz,
Kani, Verus) so the pyramid can gate CI. The agent remains responsible for
failure classification and for the Aeneas/Lean layers (extraction and the
axiom gate run in the agent flow; see colosseum-verify SKILL Layer 7-8 and
scripts/lean_axiom_gate.py).

ASSURANCE PROFILES (named, G2-scoped)
    tested   types + lints + proptests (+ fuzz when harnesses exist)
    bounded  tested + kani            (bounded proofs; bounds are per-harness)
    proved   bounded + verus + lean   (lean is NOT runnable headless: under
             this profile the headless runner always reports INCOMPLETE and
             names the layers the agent flow must supply)

VERDICT AGGREGATION (the G2 truth table, exact)
    any required layer failed                      -> FAILED      (exit 1)
    else any required layer skipped / not run /
         not_applicable                            -> INCOMPLETE  (exit 3)
    else all required layers passed                -> VERIFIED[<profile>] (exit 0)
    runner/tool infrastructure error               -> ERROR       (exit 2)

A skipped required layer is a gating gap, not a footnote: there is no
"passed with gaps". Fuzz is required only when fuzz harnesses exist;
kani/verus with zero harnesses/annotations under a profile that requires
them is INCOMPLETE (no bounded evidence is not evidence).

USAGE
    pyramid_run.py --crate <path> --profile tested|bounded|proved
        [--skip <layer>]... [--fuzz-seconds 30] [--json]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROFILES: dict[str, list[str]] = {
    "tested":  ["types", "lints", "proptests"],
    "bounded": ["types", "lints", "proptests", "kani"],
    "proved":  ["types", "lints", "proptests", "kani", "verus", "lean"],
}

TERMINAL_OK = "passed"


def aggregate_verdict(profile: str, required: list[str],
                      statuses: dict[str, str]) -> tuple[str, int]:
    """Pure G2 aggregation. `statuses` maps layer -> passed|failed|skipped|
    not_applicable|not_run. Only `required` layers gate the verdict."""
    gating = {layer: statuses.get(layer, "not_run") for layer in required}
    if any(s == "failed" for s in gating.values()):
        return "FAILED", 1
    if any(s != TERMINAL_OK for s in gating.values()):
        return "INCOMPLETE", 3
    return f"VERIFIED[{profile}]", 0


def run_cmd(cmd: list[str], cwd: Path, timeout: int = 1800) -> dict:
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout)
        return {"command": cmd, "returncode": proc.returncode,
                "duration_s": round(time.monotonic() - t0, 1),
                "stdout_preview": proc.stdout[-500:],
                "stderr_preview": proc.stderr[-500:]}
    except subprocess.TimeoutExpired:
        return {"command": cmd, "returncode": -1, "timeout": True,
                "duration_s": round(time.monotonic() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crate", required=True, type=Path)
    ap.add_argument("--profile", required=True, choices=sorted(PROFILES))
    ap.add_argument("--skip", action="append", default=[],
                    help="skip a layer (a skipped REQUIRED layer gates the "
                         "run to INCOMPLETE — visible, not forgiven)")
    ap.add_argument("--fuzz-seconds", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    crate = args.crate.resolve()
    if not (crate / "Cargo.toml").is_file():
        print(f"ERROR: no Cargo.toml at {crate}", file=sys.stderr)
        print("\nVERDICT: ERROR", file=sys.stderr)
        return 2
    if shutil.which("cargo") is None:
        print("ERROR: cargo not on PATH", file=sys.stderr)
        print("\nVERDICT: ERROR", file=sys.stderr)
        return 2

    required = list(PROFILES[args.profile])
    has_fuzz = (crate / "fuzz").is_dir()
    if has_fuzz and "fuzz" not in required:
        required.insert(3, "fuzz")  # fuzz is required exactly when harnesses exist

    layers: dict[str, dict] = {}
    statuses: dict[str, str] = {}

    def record(layer: str, status: str, detail: dict | str = "") -> None:
        statuses[layer] = status
        layers[layer] = {"status": status, "detail": detail}
        print(f"  [{status:>14}] {layer}", file=sys.stderr)

    def cargo_layer(layer: str, cmd: list[str]) -> None:
        if layer in args.skip:
            record(layer, "skipped", "skipped by flag")
            return
        r = run_cmd(cmd, crate)
        record(layer, TERMINAL_OK if r["returncode"] == 0 else "failed", r)

    cargo_layer("types", ["cargo", "check", "--quiet"])
    if statuses.get("types") == "failed":
        # Compilation failure invalidates everything downstream.
        for layer in required:
            if layer not in statuses:
                record(layer, "not_run", "types layer failed")
    else:
        cargo_layer("lints", ["cargo", "clippy", "--quiet", "--", "-D", "warnings"])
        cargo_layer("proptests", ["cargo", "test", "--quiet"])

        if "fuzz" in required or has_fuzz:
            if "fuzz" in args.skip:
                record("fuzz", "skipped", "skipped by flag")
            elif not has_fuzz:
                record("fuzz", "not_applicable", "no fuzz/ harnesses")
            elif shutil.which("cargo-fuzz") is None:
                record("fuzz", "skipped", "cargo-fuzz not installed")
            else:
                lst = run_cmd(["cargo", "fuzz", "list"], crate)
                targets = [t for t in lst.get("stdout_preview", "").split() if t]
                results = [run_cmd(["cargo", "fuzz", "run", t, "--",
                                    f"-max_total_time={args.fuzz_seconds}"],
                                   crate, timeout=args.fuzz_seconds + 300)
                           for t in targets]
                ok = targets and all(r["returncode"] == 0 for r in results)
                record("fuzz", TERMINAL_OK if ok else "failed",
                       {"targets": targets, "results": results})

        if "kani" in required:
            if "kani" in args.skip:
                record("kani", "skipped", "skipped by flag")
            elif shutil.which("cargo-kani") is None:
                record("kani", "skipped", "cargo-kani not installed")
            else:
                src = subprocess.run(["grep", "-r", "-l", "kani::proof", "src"],
                                     cwd=crate, capture_output=True, text=True)
                if src.returncode != 0:
                    record("kani", "not_applicable", "no #[kani::proof] harnesses")
                else:
                    r = run_cmd(["cargo", "kani"], crate)
                    record("kani", TERMINAL_OK if r["returncode"] == 0 else "failed", r)

        if "verus" in required:
            if "verus" in args.skip:
                record("verus", "skipped", "skipped by flag")
            elif shutil.which("cargo-verus") is None and shutil.which("verus") is None:
                record("verus", "skipped", "verus not installed")
            else:
                r = run_cmd(["cargo", "verus", "verify"], crate)
                record("verus", TERMINAL_OK if r["returncode"] == 0 else "failed", r)

        if "lean" in required:
            record("lean", "not_run",
                   "Aeneas extraction + lean_axiom_gate.py are agent-flow layers; "
                   "the headless runner cannot supply them")

    verdict, code = aggregate_verdict(args.profile, required, statuses)

    report = {
        "gate": "pyramid-headless",
        "crate": str(crate),
        "profile": args.profile,
        "required_layers": required,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "layers": layers,
        "verdict": verdict,
    }
    out_dir = crate / ".colosseum" / "verify"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"headless-{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n")

    if args.json:
        print(json.dumps(report, indent=2))
    print(f"\nreport: {out_path}", file=sys.stderr)
    print(f"VERDICT: {verdict}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
