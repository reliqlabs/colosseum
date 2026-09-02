#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""R32 - the panel-resolver extension's dispatch-identity contract.

Runs the real ``tools/panel-resolver.ts`` under Bun with a faked
``CustomToolAPI`` and a faked ``ctx.modelRegistry``, so the resolver's own logic
is exercised without an OMP session and without a single model call.

Seat resolution itself now lives in OMP (``resolvePanelLineup``), which the tool
reaches through the injected ``pi.pi`` exports. The harness locates that module
from ``OMP_SOURCE`` or from the ``omp`` on PATH and injects it, so these
assertions exercise the real delegation rather than a stand-in.

Covers the defect found by ``calibration/2026-07-24-resolver-live/``: the
resolver must emit OMP's canonical ``provider/id`` selector (``omp_panel.py``
dispatches ``resolved_model``), must record the real ``model.provider``, and
must key availability by ``provider/id`` so a model that *resolves* but whose
provider is absent is not accepted on a bare-id collision.

Exit 0 pass, 1 fail, 2 could-not-run (Bun or the OMP source absent ->
INCOMPLETE via run_all).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESOLVER = REPO / "tools" / "panel-resolver.ts"
FAILURES: list[str] = []


def omp_panel_module() -> Path | None:
    """Locate OMP's panel module: an extension package is outside its graph."""
    candidates: list[Path] = []
    source = os.environ.get("OMP_SOURCE")
    if source:
        candidates.append(Path(source))
    omp = shutil.which("omp")
    if omp:
        entry = Path(omp).resolve()
        # ~/.local/bin/omp -> <repo>/packages/coding-agent/src/cli.ts
        candidates.extend(entry.parents)
    for candidate in candidates:
        module = candidate / "packages" / "coding-agent" / "src" / "panel" / "index.ts"
        if module.is_file():
            return module
    return None

HARNESS_TS = r"""
const [, , resolverPath, projectRoot, profile, panelModule] = process.argv;
const mod = await import(resolverPath);
const injected = panelModule === "none"
  ? {}
  : { resolvePanelLineup: (await import(panelModule)).resolvePanelLineup };
const stub: any = {};
for (const key of ["min", "max", "optional", "describe", "default", "nullable", "array"]) stub[key] = () => stub;
stub.parse = (value: any) => value;
const zod: any = new Proxy(stub, { get: (target, key) => key in target ? target[key] : () => stub });
const MODELS = [
  { id: "m1", provider: "pa", identity: { class: "pa", family: "one" } },
  { id: "m1", provider: "pb", identity: { class: "pb", family: "two" } },
  { id: "m2", provider: "pb", identity: { class: "pb", family: "two" } },
  { id: "m3", provider: "pa", identity: { class: "pa", family: "one" } },
];
// `pi.pi` is OMP's injected export surface in production; the harness injects
// the real module so seat resolution is exercised, not simulated.
const api: any = { cwd: projectRoot, zod, pi: injected };
const tool = await mod.default(api);
try {
  const result = await tool.execute("tc", { profile, project_root: projectRoot }, undefined,
    { modelRegistry: { getAvailable: () => MODELS, hasConfiguredAuth: () => true } });
  console.log(JSON.stringify({ ok: true, roster: result.details, tool_name: tool.name }));
} catch (error: any) {
  console.log(JSON.stringify({ ok: false, error: String(error?.message ?? error) }));
}
"""

PROFILES = {
    "version": 1,
    "profiles": {
        # Same bare id under two providers: the exact case a bare-id selector
        # cannot express unambiguously.
        "dup": {
            "mode": "project-plan",
            "min_families": 2,
            "seats": [
                {"seat_id": "a", "declared_family": "PA", "thinking_level": "max",
                 "candidates": ["pa/m1"]},
                {"seat_id": "b", "declared_family": "PB", "thinking_level": "low",
                 "candidates": ["pb/m1"]},
            ],
            "synthesizer": {"seat_id": "s", "declared_family": "PA",
                            "thinking_level": "max", "candidates": ["pa/m1"]},
        },
        # First candidate resolves but its provider is absent from list();
        # must be skipped, falling through to the second.
        "hidden": {
            "mode": "project-plan",
            "min_families": 2,
            "seats": [
                {"seat_id": "a", "declared_family": "PZ", "thinking_level": "max",
                 "candidates": ["pz/m3", "pa/m3"]},
                {"seat_id": "b", "declared_family": "PB", "thinking_level": "max",
                 "candidates": ["pb/m2"]},
            ],
            "synthesizer": {"seat_id": "s", "declared_family": "PB",
                            "thinking_level": "max", "candidates": ["pb/m2"]},
        },
        # A bare candidate id must still come back provider-qualified.
        "bare": {
            "mode": "project-plan",
            "min_families": 2,
            "seats": [
                {"seat_id": "a", "declared_family": "PB", "thinking_level": "max",
                 "candidates": ["m2"]},
                {"seat_id": "b", "declared_family": "PA", "thinking_level": "max",
                 "candidates": ["m3"]},
            ],
            "synthesizer": {"seat_id": "s", "declared_family": "PA",
                            "thinking_level": "max", "candidates": ["m3"]},
        },
        # Distinct declared labels, same real provider -> same family token.
        "collide": {
            "mode": "project-plan",
            "min_families": 2,
            "seats": [
                {"seat_id": "a", "declared_family": "PB", "thinking_level": "max",
                 "candidates": ["pb/m1"]},
                {"seat_id": "b", "declared_family": "LooksDifferent",
                 "thinking_level": "max", "candidates": ["pb/m2"]},
            ],
            "synthesizer": {"seat_id": "s", "declared_family": "PB",
                            "thinking_level": "max", "candidates": ["pb/m1"]},
        },
        # No candidate is available at all.
        "none": {
            "mode": "project-plan",
            "min_families": 2,
            "seats": [
                {"seat_id": "a", "declared_family": "PA", "thinking_level": "max",
                 "candidates": ["pa/m1"]},
                {"seat_id": "b", "declared_family": "Ghost", "thinking_level": "max",
                 "candidates": ["nope/nothing"]},
            ],
            "synthesizer": {"seat_id": "s", "declared_family": "PA",
                            "thinking_level": "max", "candidates": ["pa/m1"]},
        },
    },
}


def check(label: str, ok: bool, detail: object = "") -> None:
    if ok:
        print(f"[ok] {label}")
    else:
        print(f"[FAIL] {label}: {detail}")
        FAILURES.append(label)


def main() -> int:
    if shutil.which("bun") is None:
        print("SKIP: bun not on PATH; cannot execute the resolver extension")
        return 2
    if not RESOLVER.is_file():
        print(f"[FAIL] resolver template missing: {RESOLVER}")
        return 1
    panel_module = omp_panel_module()
    if panel_module is None:
        print("SKIP: OMP panel module not found; set OMP_SOURCE to the oh-my-pi checkout")
        return 2

    with tempfile.TemporaryDirectory(prefix="r32-") as td:
        root = Path(td)
        (root / ".fv").mkdir()
        (root / ".fv" / "panel-profiles.json").write_text(
            json.dumps(PROFILES, indent=2) + "\n")
        harness = root / "harness.ts"
        harness.write_text(HARNESS_TS)

        def run(profile: str, inject_panel: bool = True) -> dict:
            proc = subprocess.run(
                ["bun", "run", str(harness), str(RESOLVER), str(root), profile,
                 str(panel_module) if inject_panel else "none"],
                capture_output=True, text=True, timeout=120)
            line = (proc.stdout or "").strip().splitlines()
            if not line:
                return {"ok": False, "error": f"no output (rc={proc.returncode}): "
                                             f"{proc.stderr[-400:]}"}
            try:
                return json.loads(line[-1])
            except json.JSONDecodeError:
                return {"ok": False, "error": f"unparseable: {line[-1][:300]}"}

        dup = run("dup")
        check("resolver loads under Bun and registers fv_panel_resolve",
              dup.get("ok") and dup.get("tool_name") == "fv_panel_resolve", dup)
        if dup.get("ok"):
            seats = dup["roster"]["seats"]
            # The regression: bare `model.id` would make both seats "m1".
            check("duplicate bare id resolves to distinct provider-qualified selectors",
                  [s["resolved_model"] for s in seats] == ["pa/m1", "pb/m1"], seats)
            check("resolved_provider records the real model.provider",
                  [s["resolved_provider"] for s in seats] == ["pa", "pb"], seats)
            check("synthesizer is provider-qualified too",
                  dup["roster"]["synthesizer"]["resolved_model"] == "pa/m1",
                  dup["roster"]["synthesizer"])
            check("roster names the frozen lineup with OMP's content hash",
                  isinstance(dup["roster"].get("lineup_hash"), str)
                  and dup["roster"]["lineup_hash"].startswith("sha256:")
                  and len(dup["roster"]["lineup_hash"]) == 71,
                  dup["roster"].get("lineup_hash"))
            check("thinking_level is carried per seat, unmodified",
                  [s["thinking_level"] for s in seats] == ["max", "low"], seats)
            check("resolver persists model-registry family identities for engine verification",
                  [s["resolved_family"] for s in seats] == ["pa", "pb"], seats)

        hidden = run("hidden")
        check("a resolvable model whose provider is absent is skipped "
              "(availability keyed by provider/id, not bare id)",
              hidden.get("ok")
              and hidden["roster"]["seats"][0]["resolved_model"] == "pa/m3",
              hidden)

        bare = run("bare")
        check("a bare candidate id is returned provider-qualified",
              bare.get("ok")
              and [s["resolved_model"] for s in bare["roster"]["seats"]] == ["pb/m2", "pa/m3"],
              bare)

        collide = run("collide")
        check("two seats on one real family are rejected despite distinct labels",
              not collide.get("ok")
              and "duplicate resolved model family" in collide.get("error", "")
              and "seats" in collide.get("error", ""),
              collide)

        none = run("none")
        check("a seat with no available candidate fails closed",
              not none.get("ok")
              and "nope/nothing" in none.get("error", "")
              and "unavailable" in none.get("error", ""),
              none)

        # The tool must not silently degrade on an OMP without the capability.
        legacy = run("dup", inject_panel=False)
        check("a harness without resolvePanelLineup fails closed with a capability error",
              not legacy.get("ok") and "panelLineupFreeze" in legacy.get("error", ""),
              legacy)

    if FAILURES:
        print(f"\nR32: {len(FAILURES)} failure(s)")
        return 1
    print("\nR32: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
