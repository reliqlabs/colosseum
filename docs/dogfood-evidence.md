# Dogfood evidence manifests (C9)

A dogfood evidence manifest is an immutable, per-project JSON record of what was
actually run and what was actually captured when the methodology was exercised
against a real project. It exists so a project can be cited as methodology
evidence only when its evidence is portable and checkable, not on the strength
of prose recollection.

## The rule

A project is described as a **dogfood observation** until a manifest with
`status: manifested` exists for it. Only `manifested` projects may be cited as
methodology evidence (in the README, in reports, in the coverage dashboard).
Everything else is an observation: useful, real, and driving the next iteration,
but not yet portable evidence.

- `status: observation` — a partially-captured record. Load-bearing bindings
  (commit, hashes, seeds, raw-report hashes, bounds) may be `null` because they
  were never recorded at run time. Honest nulls are required; do not backfill a
  plausible value you cannot verify.
- `status: manifested` — every required field carries a real, verifiable value:
  a pinned commit and dirty-tree hash, intent and spec hashes, exact commands,
  recorded tool and voice versions, bounds, seeds, and raw-report hashes. A
  manifest promotes from `observation` to `manifested` only by capturing the
  missing evidence, never by relabeling.

## Schema (`colosseum-dogfood-evidence/v1`)

One JSON object per project. Every listed key is required; values may be `null`
only in an `observation`-status manifest and only where the evidence was never
captured. See [`templates/dogfood-evidence.example.json`](../templates/dogfood-evidence.example.json)
for a filled-in observation.

| Field | Meaning |
|---|---|
| `schema` | `colosseum-dogfood-evidence/v1` |
| `status` | `observation` \| `manifested` (the rule above) |
| `project` | project name |
| `scope` | one-line description of what was exercised |
| `generated_at` | ISO-8601 UTC timestamp the manifest was written |
| `commits[]` | each `{ repo, commit, dirty_tree_hash, note }` exercised (G1 `source_snapshot`) |
| `intent` | `{ path, version, sha256, note }` (G1 `intent_hash`); include `version_prior_for_ledger` when a ledger lags the intent |
| `specs[]` | each `{ kind, path, version, sha256, note }` (Quint / Lean / Verus / Kani source) |
| `commands[]` | each `{ stage, command, note }`; `reference_script` when a dispatch script drove it (G1 `command`) |
| `tool_versions` | pinned tool digests; MUST carry `_cite` pointing at [`bom.json`](../bom.json) (G1 `toolchain_digests`) |
| `model_versions` | `{ _cite, voices, note }`; cite `registry/voices.json` once it exists (C4, forthcoming) |
| `bounds` | bounded-check depths (e.g. `apalache_max_steps`, `kani_unwind`) (G1 `configuration`) |
| `seeds` | per-tool seeds (e.g. `quint_run`) (G1 `seeds`) |
| `raw_reports[]` | each `{ stage, path, sha256, note }` pointing at the captured report (G1 `raw_output_hash`) |
| `canonical_paths_exercised[]` | each `{ stage, ran, evidence }`: which skills/stages ran, and which did NOT (gaps are evidence too) |
| `waivers[]` | accepted assumptions or human waivers, if any |
| `notes` | free-form provenance and honesty notes |

The manifest is a per-project provenance envelope. Its fields map onto the
per-claim G1 binding set enforced by
[`scripts/check_evidence_records.py`](../scripts/check_evidence_records.py):
`commits` → `source_snapshot`, `intent.sha256` → `intent_hash`, `tool_versions`
→ `toolchain_digests`, `bounds` → `configuration`, `seeds` → `seeds`, and
`raw_reports[].sha256` → `raw_output_hash`. The two are complementary: the
manifest records project-level provenance once, and per-claim G1 records carry
the same bindings per trust claim. `check_evidence_records.py` reads G1 record
sets, not this manifest, so it does not consume the manifest directly; a
manifest is the envelope that makes a project's G1 records reproducible.

## verified-rcv ledger regeneration

Regenerating verified-rcv's integration ledger against its current intent
(v0.3.15; the ledger was generated at v0.3.5) is pending work in the
**verified-rcv repository itself** and is out of scope for the colosseum repo.
The example manifest records the staleness as an observation; it does not
regenerate anything.

## Producing a manifest

1. Copy `templates/dogfood-evidence.example.json` into the project at
   `.colosseum/dogfood-evidence.json`.
2. Fill every field from captured evidence. Where you have no captured value,
   leave `null` and keep `status: observation`.
3. Capture the missing bindings (commit, hashes, seeds, bounds, raw-report
   hashes) on the next run, then flip `status` to `manifested`.
4. Only then may the project be cited as methodology evidence.

---

Licensed under the Apache License, Version 2.0. See [`LICENSE`](../LICENSE);
Copyright 2026 Reliq.
