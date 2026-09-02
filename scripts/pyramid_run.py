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
axiom gate run in the agent flow; see fv-verify SKILL Layer 7-8 and
scripts/lean_axiom_gate.py).

ASSURANCE PROFILES (named, G2-scoped)
    tested   types + lints + proptests + floors (+ fuzz when harnesses exist)
    bounded  tested + kani            (bounded proofs; bounds are per-harness)
    proved   bounded + verus + lean   (lean is NOT runnable headless: under
             this profile the headless runner always reports INCOMPLETE and
             names the layers the agent flow must supply)

ENGINEERING BASELINE FLOORS (C8, required under every profile)
    The `floors` layer reads <crate>/.fv/floors.json when present and
    falls back to DEFAULT_FLOORS otherwise. Three mechanical sub-checks:
      feature_matrix  cargo check over each declared --features/--no-default-
                      features/--release combo (with --workspace when the
                      crate root is a [workspace]); any combo that fails to
                      compile fails the layer. No declared matrix -> the
                      default combo is the `types` layer (not_applicable),
                      except a workspace still gets `cargo check --workspace`.
      property_bar    every src/*.rs file that exposes public API (pub fn /
                      struct / enum / trait) must carry at least
                      min_per_module in-file test functions (#[test], or only
                      proptest!/quickcheck when require_property_tests). Files
                      below the bar are listed by name and fail the layer.
      fuzz_surfaces   each parsing/deserialization surface named in floors.json
                      must have a fuzz_targets/<name>.rs target (missing ->
                      failed); the recorded fuzz duration must meet min_seconds
                      (cargo-fuzz absent -> unmeasurable -> skipped/INCOMPLETE).
    The layer's aggregate follows G2: any failed sub-check -> failed; else any
    unmeasurable (skipped) sub-check -> skipped; else passed. Named higher
    tiers (sanitizers, mutation testing, unsafe/FFI review, non-Rust per-
    surface tiers) are documentation contracts in the verify SKILL, not yet
    mechanical here.

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
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROFILES: dict[str, list[str]] = {
    "tested":  ["types", "lints", "proptests", "floors"],
    "bounded": ["types", "lints", "proptests", "floors", "kani"],
    "proved":  ["types", "lints", "proptests", "floors", "kani", "verus", "lean"],
}

TERMINAL_OK = "passed"

FLOORS_SCHEMA = "fv-floors/v2"

# Documented defaults applied when <crate>/.fv/floors.json is absent or
# omits a section. Sections present in the file layer over these.
DEFAULT_FLOORS: dict = {
    "schema": FLOORS_SCHEMA,
    "features": {"matrix": []},
    "property_tests": {"min_per_module": 1, "require_property_tests": False},
    "fuzz": {"surfaces": [], "min_seconds": 30},
}

_WORKSPACE_RE = re.compile(r"^\s*\[workspace\]", re.MULTILINE)
_PUB_ITEM_RE = re.compile(r"\bpub\s+(?:fn|struct|enum|trait)\b")
_TEST_ATTR_RE = re.compile(r"#\[\s*test\s*\]")
_PROPTEST_RE = re.compile(r"\bproptest\s*!|#\[\s*proptest\b")
_QUICKCHECK_RE = re.compile(r"\bquickcheck\s*!|#\[\s*quickcheck\b")


def load_floors(crate: Path) -> dict:
    """Read <crate>/.fv/floors.json, layering present sections over
    DEFAULT_FLOORS. Absent file -> documented defaults (a pure function)."""
    cfg = {k: (dict(v) if isinstance(v, dict) else v)
           for k, v in DEFAULT_FLOORS.items()}
    path = crate / ".fv" / "floors.json"
    if path.is_file():
        user = json.loads(path.read_text())
        if "schema" in user and user["schema"] != FLOORS_SCHEMA:
            raise ValueError(
                f"{path}: unsupported schema {user['schema']!r}; expected {FLOORS_SCHEMA!r}"
            )
        for section in ("features", "property_tests", "fuzz"):
            if isinstance(user.get(section), dict):
                cfg[section] = {**cfg[section], **user[section]}
    return cfg


def is_workspace(crate: Path) -> bool:
    """True when the crate root's Cargo.toml declares a [workspace] table."""
    toml = crate / "Cargo.toml"
    return toml.is_file() and bool(_WORKSPACE_RE.search(toml.read_text()))


def count_tests(src: str, property_only: bool = False) -> int:
    """Count test functions in a source file: proptest!/quickcheck always,
    bare #[test] only when property_only is False."""
    n = len(_PROPTEST_RE.findall(src)) + len(_QUICKCHECK_RE.findall(src))
    if not property_only:
        n += len(_TEST_ATTR_RE.findall(src))
    return n


def has_public_api(src: str) -> bool:
    """True when a file declares public API (pub fn/struct/enum/trait).
    pub(crate)/pub(super) are not public surface and do not match."""
    return bool(_PUB_ITEM_RE.search(src))


def modules_below_bar(crate: Path, cfg: dict) -> tuple[str, dict]:
    """Property-test bar: every src/*.rs file exposing public API needs at
    least min_per_module in-file test functions. Per-file is a documented
    proxy for per-public-module — idiomatic Rust unit tests live in an inline
    #[cfg(test)] mod, and attributing crate-wide tests to a module is not
    mechanically decidable. Returns (status, detail)."""
    pt = cfg.get("property_tests", {})
    minimum = int(pt.get("min_per_module", 1))
    property_only = bool(pt.get("require_property_tests", False))
    src_dir = crate / "src"
    if not src_dir.is_dir():
        return "not_applicable", {"reason": "no src/ directory"}
    public_modules: list[str] = []
    below: list[str] = []
    for f in sorted(src_dir.rglob("*.rs")):
        text = f.read_text(errors="replace")
        if not has_public_api(text):
            continue
        rel = str(f.relative_to(crate))
        public_modules.append(rel)
        if count_tests(text, property_only) < minimum:
            below.append(rel)
    detail = {"min_per_module": minimum, "require_property_tests": property_only,
              "public_modules": public_modules, "below_bar": below}
    if not public_modules:
        return "not_applicable", {"reason": "no public modules under src/", **detail}
    return ("failed" if below else TERMINAL_OK), detail


def fuzz_surface_check(crate: Path, surfaces: list[str], min_seconds: int,
                       fuzz_layer: dict | None) -> tuple[str, dict]:
    """Fuzz-time floor. Each named surface needs a fuzz_targets/<name>.rs
    target (missing -> failed, a structural fact independent of cargo-fuzz).
    The duration floor is read from the runner's fuzz layer; when cargo-fuzz
    is absent the fuzz layer did not run to completion, so the duration is
    unmeasurable -> skipped (INCOMPLETE), never a silent pass."""
    if not surfaces:
        return "not_applicable", {"surfaces": []}
    targets_dir = crate / "fuzz" / "fuzz_targets"
    missing = [s for s in surfaces if not (targets_dir / f"{s}.rs").is_file()]
    if missing:
        return "failed", {"surfaces": surfaces, "missing_targets": missing}
    fstatus = (fuzz_layer or {}).get("status")
    if fstatus != TERMINAL_OK:
        return "skipped", {"surfaces": surfaces, "min_seconds": min_seconds,
                           "reason": f"fuzz duration unmeasurable "
                                     f"(fuzz layer status={fstatus})"}
    durations = ((fuzz_layer or {}).get("detail") or {}).get("durations", {})
    short = [s for s in surfaces if durations.get(s, 0) < min_seconds]
    if short:
        return "failed", {"surfaces": surfaces, "min_seconds": min_seconds,
                          "below_floor": short, "durations": durations}
    return TERMINAL_OK, {"surfaces": surfaces, "min_seconds": min_seconds,
                         "durations": durations}


def floors_layer(crate: Path, cfg: dict, workspace: bool,
                 fuzz_layer: dict | None) -> tuple[str, dict]:
    """Run the three floor sub-checks and aggregate per G2 (failed dominates;
    else unmeasurable/skipped; else passed). Returns (status, detail)."""
    subchecks: dict[str, dict] = {}

    matrix = cfg.get("features", {}).get("matrix") or []
    if not matrix:
        if workspace:
            r = run_cmd(["cargo", "check", "--workspace", "--quiet"], crate)
            subchecks["feature_matrix"] = {
                "status": TERMINAL_OK if r["returncode"] == 0 else "failed",
                "combos": [{"name": "workspace-default", "result": r}]}
        else:
            subchecks["feature_matrix"] = {
                "status": "not_applicable",
                "reason": "no matrix declared; default combo is the types layer"}
    else:
        combos = []
        fm_status = TERMINAL_OK
        for combo in matrix:
            cmd = ["cargo", "check", "--quiet"]
            if workspace:
                cmd.append("--workspace")
            if combo.get("no_default_features"):
                cmd.append("--no-default-features")
            feats = combo.get("features") or []
            if feats:
                cmd += ["--features", ",".join(feats)]
            if combo.get("release"):
                cmd.append("--release")
            r = run_cmd(cmd, crate)
            if r["returncode"] != 0:
                fm_status = "failed"
            combos.append({"name": combo.get("name") or ",".join(feats) or "default",
                           "release": bool(combo.get("release")), "result": r})
        subchecks["feature_matrix"] = {"status": fm_status, "combos": combos}

    pb_status, pb_detail = modules_below_bar(crate, cfg)
    subchecks["property_bar"] = {"status": pb_status, **pb_detail}

    fuzz_cfg = cfg.get("fuzz", {})
    fz_status, fz_detail = fuzz_surface_check(
        crate, fuzz_cfg.get("surfaces") or [],
        int(fuzz_cfg.get("min_seconds", 30)), fuzz_layer)
    subchecks["fuzz_surfaces"] = {"status": fz_status, **fz_detail}

    statuses = [v["status"] for v in subchecks.values()]
    if "failed" in statuses:
        agg = "failed"
    elif "skipped" in statuses:
        agg = "skipped"
    else:
        agg = TERMINAL_OK
    return agg, {"floors_schema": cfg.get("schema"), "workspace": workspace,
                 "subchecks": subchecks}


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
                durations = {t: r.get("duration_s", 0)
                             for t, r in zip(targets, results)}
                record("fuzz", TERMINAL_OK if ok else "failed",
                       {"targets": targets, "durations": durations,
                        "results": results})

        if "floors" in required:
            if "floors" in args.skip:
                record("floors", "skipped", "skipped by flag")
            else:
                try:
                    cfg = load_floors(crate)
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    record("floors", "failed", {"error": str(error)})
                else:
                    status, detail = floors_layer(
                        crate, cfg, is_workspace(crate), layers.get("fuzz"))
                    record("floors", status, detail)

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
        "floors": layers.get("floors", {}).get("detail", {}),
        "verdict": verdict,
    }
    out_dir = crate / ".fv" / "verify"
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
