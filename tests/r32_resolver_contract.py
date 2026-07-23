#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""R32 - the panel-resolver extension's dispatch-identity contract.

Runs the real ``templates/omp-panel-resolver.ts`` under Bun with a faked
``ExtensionAPI`` and a faked ``ctx.models``, so the resolver's own logic is
exercised without an OMP session and without a single model call.

Covers the defect found by ``calibration/2026-07-24-resolver-live/``: the
resolver must emit OMP's canonical ``provider/id`` selector (``omp_panel.py``
dispatches ``resolved_model``), must record the real ``model.provider``, and
must key availability by ``provider/id`` so a model that *resolves* but whose
provider is absent is not accepted on a bare-id collision.

Exit 0 pass, 1 fail, 2 could-not-run (Bun absent -> INCOMPLETE via run_all).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESOLVER = REPO / "templates" / "omp-panel-resolver.ts"
FAILURES: list[str] = []

HARNESS_TS = r"""
const [, , resolverPath, projectRoot, profile] = process.argv;
const mod = await import(resolverPath);

const stub: any = {};
for (const k of ["min", "max", "optional", "describe", "default", "nullable", "array"]) {
	stub[k] = () => stub;
}
stub.parse = (x: any) => x;
const z: any = new Proxy(stub, { get: (t, p) => (p in t ? t[p] : () => stub) });

const MODELS = [
	{ id: "m1", provider: "pa" },
	{ id: "m1", provider: "pb" },
	{ id: "m2", provider: "pb" },
	{ id: "m3", provider: "pa" },
];
// Resolvable but NOT in list(): a bare-id availability set would accept it
// because an unrelated provider ("pa") also serves id "m3".
const HIDDEN = { id: "m3", provider: "pz" };

let tool: any = null;
const pi: any = {
	zod: { z },
	setLabel() {},
	registerTool(t: any) {
		tool = t;
	},
	on() {},
};
mod.default(pi);
if (!tool) {
	console.log(JSON.stringify({ ok: false, error: "registerTool was never called" }));
	process.exit(0);
}

const ctx: any = {
	cwd: projectRoot,
	models: {
		list: () => MODELS,
		resolve: (spec: string) => {
			if (spec === "pz/m3") return HIDDEN;
			const qualified = MODELS.find((m) => `${m.provider}/${m.id}` === spec);
			if (qualified) return qualified;
			return MODELS.find((m) => m.id === spec);
		},
		// Family keyed by provider: distinct providers are distinct lineages.
		family: (m: any) => `fam:${m.provider}`,
	},
};

try {
	const res = await tool.execute("tc", { profile, project_root: projectRoot }, undefined, undefined, ctx);
	console.log(JSON.stringify({ ok: true, roster: res.details, tool_name: tool.name }));
} catch (err: any) {
	console.log(JSON.stringify({ ok: false, error: String(err?.message ?? err) }));
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

    with tempfile.TemporaryDirectory(prefix="r32-") as td:
        root = Path(td)
        (root / ".colosseum").mkdir()
        (root / ".colosseum" / "panel-profiles.json").write_text(
            json.dumps(PROFILES, indent=2) + "\n")
        harness = root / "harness.ts"
        harness.write_text(HARNESS_TS)

        def run(profile: str) -> dict:
            proc = subprocess.run(
                ["bun", "run", str(harness), str(RESOLVER), str(root), profile],
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
        check("resolver loads under Bun and registers colosseum_panel_resolve",
              dup.get("ok") and dup.get("tool_name") == "colosseum_panel_resolve", dup)
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
            check("thinking_level is carried per seat, unmodified",
                  [s["thinking_level"] for s in seats] == ["max", "low"], seats)
            check("family distinctness is reported as a runtime comparison",
                  dup["roster"]["family_distinctness_checked"] is True
                  and "ctx.models.family" in dup["roster"]["family_distinctness_source"],
                  dup["roster"].get("family_distinctness_source"))
            check("opaque family token is never persisted in the roster",
                  "fam:" not in json.dumps(dup["roster"]), dup["roster"])

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
              not collide.get("ok") and "same model family" in collide.get("error", ""),
              collide)

        none = run("none")
        check("a seat with no available candidate fails closed",
              not none.get("ok") and "no available model" in none.get("error", ""),
              none)

    if FAILURES:
        print(f"\nR32: {len(FAILURES)} failure(s)")
        return 1
    print("\nR32: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
