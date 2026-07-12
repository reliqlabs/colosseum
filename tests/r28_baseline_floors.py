#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R28 — engineering baseline floors (C8).

The `floors` layer is a required layer under every profile (tested, and
therefore bounded/proved). It reads <crate>/.colosseum/floors.json (documented
defaults when absent) and runs three mechanical sub-checks: a cargo feature
matrix (with --workspace on workspaces), a per-public-module property-test bar,
and a per-surface fuzz-time floor. This suite drives the pure floor helpers
directly, then runs the headless runner end-to-end against fixture crates:

  below/          public module with zero in-file tests + a floors.json fuzz
                  surface with no target -> floors FAILED, run FAILED (exit 1)
  compliant/      in-file test, compiling feature matrix, no fuzz surfaces ->
                  floors passed, run VERIFIED[tested] (exit 0)
  featurefail/    a floors.json feature combo fails cargo check -> floors
                  FAILED via the feature-matrix sub-check, run FAILED (exit 1)
  fuzzunmeasured/ named surface has a target but cargo-fuzz is absent -> the
                  fuzz-time floor is unmeasurable -> floors skipped,
                  run INCOMPLETE (exit 3)
  <defaults>      the R20 minicrate (no floors.json) exercises the default
                  floors: property bar met by its inline #[test], no matrix,
                  no fuzz -> floors passed, run VERIFIED[tested] (exit 0)

Requires cargo. Exit 0 pass, 1 fail, 2 toolchain unavailable.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "scripts" / "pyramid_run.py"
FIX = REPO / "tests" / "fixtures" / "r28"
MINICRATE = REPO / "tests" / "fixtures" / "r20" / "minicrate"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def load_runner():
    spec = importlib.util.spec_from_file_location("pyramid_run", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(crate: Path, profile: str, *extra: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["uv", "run", "--script", str(RUNNER), "--crate", str(crate),
         "--profile", profile, *extra],
        capture_output=True, text=True, timeout=900,
    )
    return proc.returncode, proc.stdout + proc.stderr


def floors_status(crate: Path) -> tuple[str, dict]:
    """Read the layer status and sub-check statuses from the persisted report."""
    reports = sorted((crate / ".colosseum" / "verify").glob("headless-*.json"))
    report = json.loads(reports[-1].read_text())
    floors = report["layers"].get("floors", {})
    subs = {k: v["status"]
            for k, v in floors.get("detail", {}).get("subchecks", {}).items()}
    return floors.get("status", "MISSING"), subs


def test_pure(mod) -> None:
    print("pure floor helpers")

    # load_floors: absent file -> documented defaults.
    d = mod.load_floors(Path("/definitely/not/a/crate"))
    check("load_floors: absent floors.json -> defaults",
          d["property_tests"]["min_per_module"] == 1
          and d["fuzz"]["min_seconds"] == 30
          and d["features"]["matrix"] == []
          and d["schema"] == "colosseum-floors/v1", str(d))

    # load_floors: present file layers over defaults, keeps default sub-keys.
    with tempfile.TemporaryDirectory(prefix="r28-lf-") as td:
        crate = Path(td)
        (crate / ".colosseum").mkdir()
        (crate / ".colosseum" / "floors.json").write_text(
            json.dumps({"property_tests": {"min_per_module": 3}}))
        d = mod.load_floors(crate)
        check("load_floors: file section overrides default, keeps sibling keys",
              d["property_tests"]["min_per_module"] == 3
              and d["property_tests"]["require_property_tests"] is False,
              str(d["property_tests"]))

    # is_workspace.
    with tempfile.TemporaryDirectory(prefix="r28-ws-") as td:
        crate = Path(td)
        (crate / "Cargo.toml").write_text("[workspace]\nmembers = []\n")
        check("is_workspace: [workspace] table detected", mod.is_workspace(crate))
        (crate / "Cargo.toml").write_text("[package]\nname = \"x\"\n")
        check("is_workspace: plain package is not a workspace",
              not mod.is_workspace(crate))

    # count_tests / has_public_api.
    src_test = "#[test]\nfn a() {}\n"
    check("count_tests: #[test] counted", mod.count_tests(src_test) == 1)
    check("count_tests: property_only excludes bare #[test]",
          mod.count_tests(src_test, property_only=True) == 0)
    check("count_tests: proptest!/quickcheck counted under property_only",
          mod.count_tests("proptest! { fn p() {} }\nquickcheck! { fn q() {} }",
                          property_only=True) == 2)
    check("has_public_api: pub fn is public surface",
          mod.has_public_api("pub fn f() {}"))
    check("has_public_api: pub(crate) is not public surface",
          not mod.has_public_api("pub(crate) fn f() {}"))

    # modules_below_bar over the fixtures.
    status, detail = mod.modules_below_bar(FIX / "below", mod.load_floors(FIX / "below"))
    check("modules_below_bar: below fixture fails, names the module",
          status == "failed" and detail["below_bar"] == ["src/lib.rs"], str(detail))
    status, _ = mod.modules_below_bar(FIX / "compliant",
                                      mod.load_floors(FIX / "compliant"))
    check("modules_below_bar: compliant fixture passes", status == "passed", status)
    status, _ = mod.modules_below_bar(MINICRATE, mod.load_floors(MINICRATE))
    check("modules_below_bar: R20 minicrate passes under defaults",
          status == "passed", status)
    # require_property_tests raises the bar: compliant has only #[test].
    strict = mod.load_floors(FIX / "compliant")
    strict["property_tests"]["require_property_tests"] = True
    status, detail = mod.modules_below_bar(FIX / "compliant", strict)
    check("modules_below_bar: require_property_tests rejects bare #[test]",
          status == "failed" and detail["below_bar"] == ["src/lib.rs"], str(detail))

    # fuzz_surface_check.
    status, _ = mod.fuzz_surface_check(FIX / "below", [], 30, None)
    check("fuzz_surface_check: no surfaces -> not_applicable",
          status == "not_applicable", status)
    status, detail = mod.fuzz_surface_check(FIX / "below", ["parse_surface"], 30, None)
    check("fuzz_surface_check: named surface with no target -> failed",
          status == "failed" and detail["missing_targets"] == ["parse_surface"],
          str(detail))
    status, _ = mod.fuzz_surface_check(FIX / "fuzzunmeasured", ["parse_input"], 30, None)
    check("fuzz_surface_check: target present, no fuzz run -> skipped (unmeasurable)",
          status == "skipped", status)
    passed_layer = {"status": "passed", "detail": {"durations": {"parse_input": 45}}}
    status, _ = mod.fuzz_surface_check(FIX / "fuzzunmeasured", ["parse_input"], 30,
                                       passed_layer)
    check("fuzz_surface_check: duration above floor -> passed", status == "passed",
          status)
    short_layer = {"status": "passed", "detail": {"durations": {"parse_input": 5}}}
    status, detail = mod.fuzz_surface_check(FIX / "fuzzunmeasured", ["parse_input"],
                                            30, short_layer)
    check("fuzz_surface_check: duration below floor -> failed",
          status == "failed" and detail["below_floor"] == ["parse_input"], str(detail))


def test_runner() -> None:
    print("headless runner (floors as a required layer under `tested`)")
    with tempfile.TemporaryDirectory(prefix="r28-run-") as td:
        tmp = Path(td)

        below = tmp / "below"
        shutil.copytree(FIX / "below", below)
        code, out = run(below, "tested")
        st, subs = floors_status(below)
        check("below floors: run FAILED, exit 1", code == 1 and "FAILED" in out,
              f"exit={code}")
        check("below floors: floors layer failed on property bar + fuzz surface",
              st == "failed" and subs.get("property_bar") == "failed"
              and subs.get("fuzz_surfaces") == "failed", f"{st} {subs}")

        compliant = tmp / "compliant"
        shutil.copytree(FIX / "compliant", compliant)
        code, out = run(compliant, "tested")
        st, _ = floors_status(compliant)
        check("compliant floors: run VERIFIED[tested], exit 0",
              code == 0 and "VERIFIED[tested]" in out, f"exit={code}")
        check("compliant floors: floors layer passed", st == "passed", st)

        featurefail = tmp / "featurefail"
        shutil.copytree(FIX / "featurefail", featurefail)
        code, out = run(featurefail, "tested")
        st, subs = floors_status(featurefail)
        check("featurefail floors: feature-matrix combo fails -> run FAILED, exit 1",
              code == 1 and "FAILED" in out, f"exit={code}")
        check("featurefail floors: floors failed on the feature-matrix sub-check",
              st == "failed" and subs.get("feature_matrix") == "failed",
              f"{st} {subs}")

        # Absent floors.json: the R20 minicrate under documented defaults.
        defaults = tmp / "defaults"
        shutil.copytree(MINICRATE, defaults)
        check("defaults: minicrate carries no floors.json",
              not (defaults / ".colosseum" / "floors.json").exists())
        code, out = run(defaults, "tested")
        st, subs = floors_status(defaults)
        check("defaults: absent floors.json -> VERIFIED[tested], exit 0",
              code == 0 and "VERIFIED[tested]" in out, f"exit={code}")
        check("defaults: floors passed (property bar met, matrix/fuzz not_applicable)",
              st == "passed" and subs.get("property_bar") == "passed"
              and subs.get("feature_matrix") == "not_applicable"
              and subs.get("fuzz_surfaces") == "not_applicable", f"{st} {subs}")

        # cargo-fuzz absent: the fuzz-time floor is unmeasurable, not a pass.
        fuzzun = tmp / "fuzzunmeasured"
        shutil.copytree(FIX / "fuzzunmeasured", fuzzun)
        code, out = run(fuzzun, "tested")
        st, subs = floors_status(fuzzun)
        check("fuzzunmeasured: cargo-fuzz absent -> run INCOMPLETE, exit 3",
              code == 3 and "INCOMPLETE" in out, f"exit={code}")
        check("fuzzunmeasured: floors skipped on the unmeasurable fuzz surface",
              st == "skipped" and subs.get("fuzz_surfaces") == "skipped",
              f"{st} {subs}")


def main() -> int:
    mod = load_runner()
    test_pure(mod)

    if shutil.which("cargo") is None:
        print("SKIP-FAIL: cargo not on PATH; live-runner half skipped",
              file=sys.stderr)
        return 2
    test_runner()

    print()
    if FAILURES:
        print(f"R28: {len(FAILURES)} failure(s)")
        return 1
    print("R28: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
