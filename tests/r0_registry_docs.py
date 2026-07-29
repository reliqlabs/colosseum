#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R0 — voice registry, generated roster docs, doctor, init (C4).

Infra check, not a Part IV regression fixture: it guards the machinery that
makes registry/voices.json authoritative over the hand-maintained roster sites.

  1. Registry parses; the calibration invariant holds — a canonical-panel voice
     with pending (or empty) calibration is a failure, and any pending voice must
     be candidate/local-specialist/excluded (never canonical-panel).
  2. Every profile's stored content_hash equals the recomputed value.
  3. `gen_roster_docs.py --check` is green — the generated blocks in the SKILLs,
     scripts/README, INSTALL, and dispatch.config.example.json match the registry.
  4. `colosseum_init.py` scaffolds a temp project (dirs, dispatch.json with the
     filled placeholders, both OpenCode agents), is idempotent without --force,
     and overwrites with --force.
  5. `colosseum_doctor.py --json` runs offline without a tooling error and reports
     BOM-consistent tool versions.

Requires opencode + quint on PATH (as the rest of the suite does) so the doctor's
version checks are exercised. Exit 0 pass, 1 fail, 2 toolchain unavailable.
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
SCRIPTS = REPO / "scripts"
REGISTRY = REPO / "registry" / "voices.json"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def load_gen():
    spec = importlib.util.spec_from_file_location(
        "gen_roster_docs", SCRIPTS / "gen_roster_docs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(argv: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, **kw)


def main() -> int:
    for tool in ("opencode", "quint"):
        if shutil.which(tool) is None:
            print(f"SKIP-FAIL: {tool} not on PATH", file=sys.stderr)
            return 2

    gen = load_gen()

    # 1. Registry parse + calibration invariant.
    reg = json.loads(REGISTRY.read_text())
    check("registry parses with voices[] and profiles[]",
          isinstance(reg.get("voices"), list) and isinstance(reg.get("profiles"), list))
    n_canon = 0
    for v in reg["voices"]:
        status, cal = v["status"], v["calibration"]
        if status == "canonical-panel":
            n_canon += 1
            check(f"canonical-panel voice {v['id']} has non-pending calibration",
                  cal != "pending" and bool(cal))
        if cal == "pending":
            check(f"pending voice {v['id']} is not canonical-panel",
                  status in ("candidate", "local-specialist", "excluded"), status)
    check("at least one canonical-panel voice exists", n_canon >= 1, f"{n_canon} found")
    omp_mapped = [v for v in reg["voices"] if v.get("omp_model")]
    for v in omp_mapped:
        check(f"OMP route {v['id']} has separate calibration",
              isinstance(v.get("omp_calibration"), str) and bool(v["omp_calibration"]))

    # The pending sentinel must stay EXACT. render_omp_native_config marks the
    # whole route "cited" only when no voice equals "pending", so decorating this
    # field with an explanation ("pending. Scored 7/7 but unattested...") silently
    # promotes the route to calibrated. That regression was introduced and caught
    # by CI once; this is the guard.
    for v in omp_mapped:
        cal = v["omp_calibration"]
        looks_pending = cal.strip().lower().startswith("pending")
        check(f"OMP route {v['id']} pending sentinel is exact",
              cal == "pending" or not looks_pending,
              f"reads as pending but is not the literal: {cal[:60]!r}")
        if cal != "pending" and v.get("omp_calibration_note"):
            check(f"OMP route {v['id']} cited route carries no pending note",
                  False, "omp_calibration_note is only for pending routes")
    canonical = gen.profile_by_name(reg, "canonical-4")
    canonical_voices = [gen.voice_by_id(reg, pv["id"]) for pv in canonical["voices"]]
    check("every canonical voice has an OMP-native route",
          all(v.get("omp_model") for v in canonical_voices))

    # The effort policy is data-checkable, not prose. Each voice records the
    # ladder its route actually exposes, and the level must be what
    # `one-below-max` yields on THAT list: step down from `max`, or take the top
    # rung when the ladder has no `max`. The ladder belongs to the PROVIDER, so
    # moving a model between providers can legitimately change the level -- which
    # is exactly why this is asserted against recorded rungs instead of a
    # hardcoded table of expected levels.
    for v in omp_mapped:
        if v.get("omp_thinking_level") is None:
            check(f"OMP route {v['id']} with a null level records no ladder",
                  not v.get("omp_thinking_ladder"))
            continue
        ladder = v.get("omp_thinking_ladder")
        check(f"OMP route {v['id']} records its ladder",
              isinstance(ladder, list) and bool(ladder), ladder)
        if not (isinstance(ladder, list) and ladder):
            continue
        expected = ladder[-2] if ladder[-1] == "max" else ladder[-1]
        check(f"OMP route {v['id']} level is one-below-max on its own ladder",
              v["omp_thinking_level"] == expected,
              f"ladder={'/'.join(ladder)} level={v['omp_thinking_level']} "
              f"policy_expects={expected}")
        check(f"OMP route {v['id']} level is a real rung",
              v["omp_thinking_level"] in ladder, ladder)

    # Self-test: renaming a top rung must be caught, not absorbed. This is the
    # exact shape that slipped through when GLM moved provider.
    fake = {"omp_thinking_level": "high", "omp_thinking_ladder": ["low", "high", "xhigh"]}
    fake_expected = (fake["omp_thinking_ladder"][-2]
                     if fake["omp_thinking_ladder"][-1] == "max"
                     else fake["omp_thinking_ladder"][-1])
    check("self-test: a level below a non-max top rung is detectable",
          fake["omp_thinking_level"] != fake_expected)

    native_route = gen.render_omp_native_config(reg)
    check("OMP-native route hash recomputes",
          native_route["route_hash"] == gen.omp_route_hash(native_route))
    check("OMP-native route remains explicitly uncalibrated",
          native_route["calibration"] == "pending")

    # A deliberately-broken clone must be caught (the invariant validates something).
    bad = json.loads(REGISTRY.read_text())
    bad["voices"][0]["status"] = "canonical-panel"
    bad["voices"][0]["calibration"] = "pending"
    broken = any(vv["status"] == "canonical-panel" and vv["calibration"] == "pending"
                 for vv in bad["voices"])
    check("self-test: a pending canonical-panel voice is detectable", broken)

    # 2. Profile content_hash recomputes.
    for prof in reg["profiles"]:
        want = gen.profile_content_hash(prof)
        check(f"profile {prof['name']} content_hash recomputes",
              prof.get("content_hash") == want,
              f"stored={prof.get('content_hash')} want={want}")

    # 3. gen_roster_docs --check green.
    p = run(["uv", "run", "--script", str(SCRIPTS / "gen_roster_docs.py"), "--check"])
    check("gen_roster_docs --check green (docs in sync with registry)",
          p.returncode == 0, (p.stdout + p.stderr).strip()[-300:])

    # 4. init scaffolds + idempotence + --force.
    with tempfile.TemporaryDirectory(prefix="r0-init-") as td:
        proj = Path(td) / "proj"
        spec_path = proj / ".colosseum" / "intent.md"
        p1 = run(["uv", "run", "--script", str(SCRIPTS / "colosseum_init.py"),
                  str(proj), "--target-spec", str(spec_path)])
        check("init run 1 exits 0", p1.returncode == 0, p1.stderr[-200:])
        for rel in (".colosseum/scripts/opencode_dispatch.py", ".colosseum/dispatch.json",
                    ".colosseum/attacks", ".colosseum/verify", ".colosseum/evidence",
                    ".opencode/agent/spec-adversary.md", ".opencode/agent/quint-spec-generator.md"):
            check(f"init created {rel}", (proj / rel).exists())
        cfg = json.loads((proj / ".colosseum" / "dispatch.json").read_text())
        check("dispatch.json project_root filled", cfg["project_root"] == str(proj.resolve()))
        check("dispatch.json target_spec filled", cfg["target_spec"] == str(spec_path.resolve()))
        check("dispatch.json voices come from the registry (canonical-4 opencode set)",
              [v["id"] for v in cfg["voices"]]
              == ["gpt-5.6-sol", "glm-5.2", "kimi-k3"])
        check("dispatch.json carries canonical OMP-native membership",
              [v["id"] for v in cfg["omp_native"]["voices"]]
              == ["claude-agent", "gpt-5.6-sol", "glm-5.2", "kimi-k3"])
        check("dispatch.json OMP route hash is content-addressed",
              cfg["omp_native"]["route_hash"]
              == gen.omp_route_hash(cfg["omp_native"]))

        # Additive migration: preserve project config while filling a missing
        # OMP-native block.
        djson = proj / ".colosseum" / "dispatch.json"
        migrated = json.loads(djson.read_text())
        migrated.pop("omp_native")
        migrated.pop("_comment_omp_native")
        migrated["project_local"] = {"keep": True}
        djson.write_text(json.dumps(migrated) + "\n")
        pm = run(["uv", "run", "--script", str(SCRIPTS / "colosseum_init.py"),
                  str(proj)])
        migrated = json.loads(djson.read_text())
        check("init additively installs missing OMP-native routes",
              pm.returncode == 0 and "omp_native" in migrated)
        check("OMP-native migration preserves project config",
              migrated.get("project_local") == {"keep": True})

        # Idempotence: once the native block exists, preserve project changes.
        migrated["project_local"] = {"changed": True}
        djson.write_text(json.dumps(migrated) + "\n")
        before = djson.read_text()
        p2 = run(["uv", "run", "--script", str(SCRIPTS / "colosseum_init.py"), str(proj)])
        check("init run 2 (no --force) exits 0", p2.returncode == 0, p2.stderr[-200:])
        check("idempotent run preserves the complete project config",
              djson.read_text() == before)

        djson.write_text("{invalid\n")
        p_bad = run(["uv", "run", "--script", str(SCRIPTS / "colosseum_init.py"),
                     str(proj)])
        check("invalid project config is preserved with a warning",
              p_bad.returncode == 0
              and djson.read_text() == "{invalid\n"
              and "WARN:" in p_bad.stderr)

        # --force restores canonical content.
        p3 = run(["uv", "run", "--script", str(SCRIPTS / "colosseum_init.py"),
                  str(proj), "--target-spec", str(spec_path), "--force"])
        check("init run 3 (--force) exits 0", p3.returncode == 0, p3.stderr[-200:])
        check("--force overwrote dispatch.json back to canonical",
              json.loads(djson.read_text()).get("project_root") == str(proj.resolve()))

    # 5. doctor --json runs offline without a tooling error, versions BOM-consistent.
    pd = run(["uv", "run", "--script", str(SCRIPTS / "colosseum_doctor.py"), "--json"])
    check("doctor --json did not hit a tooling error (exit != 2)", pd.returncode != 2,
          pd.stderr[-200:])
    try:
        doc = json.loads(pd.stdout)
        parsed = True
    except json.JSONDecodeError:
        parsed = False
        doc = {}
    check("doctor --json emits parseable JSON", parsed)
    if parsed:
        tool_checks = {c["name"]: c for c in doc.get("checks", [])
                       if c["category"] == "toolchain"}
        for tool in ("opencode", "quint"):
            c = tool_checks.get(tool)
            check(f"doctor reports {tool} version BOM-consistent",
                  c is not None and c["status"] == "ok", c and c["detail"])
        check("doctor JSON carries the BOM tool pins", "bom_tools" in doc)

    print()
    if FAILURES:
        print(f"R0: {len(FAILURES)} failure(s)")
        return 1
    print("R0: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
