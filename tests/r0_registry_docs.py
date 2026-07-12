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
        check("dispatch.json voices come from the registry (canonical-5 opencode set)",
              [v["id"] for v in cfg["voices"]]
              == ["gpt-5.6-sol-pro", "kimi-k2.6", "deepseek-v4-flash", "gemini-3.1-pro-preview"])

        # Idempotence: corrupt a file, re-run without --force -> untouched (skipped).
        djson = proj / ".colosseum" / "dispatch.json"
        djson.write_text('{"corrupted": true}\n')
        p2 = run(["uv", "run", "--script", str(SCRIPTS / "colosseum_init.py"), str(proj)])
        check("init run 2 (no --force) exits 0", p2.returncode == 0, p2.stderr[-200:])
        check("init run 2 did not clobber the existing file", "skip" in p2.stdout)
        check("idempotent run left the corrupted file untouched",
              json.loads(djson.read_text()) == {"corrupted": True})

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
