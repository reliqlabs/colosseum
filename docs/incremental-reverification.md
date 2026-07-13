# Incremental re-verification and the ledger envelope (M5)

Scaffolding for the system-of-intents change loop. This document defines the
ledger schema envelope, the rule for reusing component evidence when a system
changes, and how the assurance tiers map onto non-Rust components. It is the
reference the `colosseum-boundary` skill and `colosseum-change` point at when
they bound the blast radius of a change.

Status: the bidboard system-of-intents run this scaffolding is built for has
NOT been run. This document specifies the mechanism; no system verdict is
claimed here.

## The ledger envelope

The two-gate ledger (C1) consumes G1 evidence records. On their own, records are
a bare JSON list. M5 wraps a record set in a versioned envelope:

```json
{
  "ledger_schema_version": "colosseum-ledger/v1",
  "records": [ { "claim_id": "...", "...": "..." } ]
}
```

- A bare list (or a bare single record object) is **unversioned** (`unversioned/v0`).
  It is still valid input to the gates; the difference is that an unversioned
  ledger cannot participate in schema-aware reuse below.
- `scripts/check_ledger_version.py` validates only the envelope's version field:
  exit 0 for a recognized version or for a bare/unversioned ledger (with a
  warning), exit 2 for an object that carries a `ledger_schema_version` the
  toolchain does not know, or that carries a `records` key with no version.
- `scripts/check_evidence_records.py` and `scripts/coverage_dashboard.py` both
  read either shape: their `unwrap` step flattens an envelope to its `records`
  list, so a versioned ledger and its equivalent bare list gate to the identical
  verdict. The version field never changes a verdict; it only lets a change-loop
  pass tell a schema migration apart from an ordinary source change.

Recognized versions live in `check_ledger_version.py`'s `KNOWN_VERSIONS`. A new
schema version is added there deliberately, the same way tool pins move in
`bom.json`: a forward-incompatible ledger fails loudly rather than being read
under the wrong assumptions.

## What a change invalidates

A G1 record binds its evidence to a `source_snapshot` (commit plus dirty-tree
content hash), an `intent_hash`, an `obligation_manifest_hash`, a `profile`, a
toolchain digest set, and the exact command, configuration, and seeds. Any of
these drifting makes the record stale. For a single component the rule is: if the
component's `source_snapshot` no longer matches the tree, its records must be
re-earned.

Decomposition (via `colosseum-boundary`) turns that per-component rule into a
bounded re-verification strategy for the whole system. When a system changes,
re-verify only:

1. **Every component whose own source changed.** Its `source_snapshot` binding is
   stale, so its records are stale, regardless of its neighbors.
2. **Every component that assumes (`A*`) a guarantee (`G*`) whose meaning
   changed.** A neighbor discharges the assumption; if that neighbor's guarantee
   is unchanged in effect, the assumption still holds and the assuming
   component's evidence is reusable. If the guarantee changed, the assumption is
   in question and the assuming component re-runs.

A component's evidence is **reusable across a system change** exactly when both
hold:

- its `source_snapshot` binding still matches the current tree for that
  component, and
- every `A*` clause it depends on is still discharged by an unchanged `G*` clause
  (or a still-waived `K*` trust assumption).

Everything else re-runs. The `ledger_schema_version` is checked first: a schema
migration invalidates the reuse computation itself (the record shape changed), so
a version bump forces a full re-verification pass regardless of source snapshots.

### Worked shape

Given components C1, C2, C3 with `G1(C1) ⟶ A1(C2)` and `G3(C3) ⟶ A2(C1)`:

- Edit only C3's internals, C3's guarantee `G3` unchanged in effect: re-verify C3
  (source changed); C1 reuses (its `A2` still discharged by an unchanged `G3`);
  C2 reuses (untouched). Blast radius: 1 of 3.
- Edit C1 in a way that changes `G1`: re-verify C1 (source changed) and C2 (its
  `A1` rests on the changed `G1`). C3 reuses. Blast radius: 2 of 3.
- Bump `ledger_schema_version`: re-verify all. Blast radius: 3 of 3.

The composition itself is recorded as a G1 record whose `required_targets` are the
boundary obligations (the `A*`-discharged-by-`G*` pairs), so the system verdict is
re-derivable from the reused component records plus the (possibly re-run) changed
ones, under the same G2 truth table.

## Non-Rust assurance tiers

The assurance profiles are contracts on evidence strength, not Rust bindings.
A component reaches a tier with whatever tool delivers that strength for its
language. The tiers are:

- **tested** — types plus lints plus property tests plus a fuzz surface, per the
  engineering floors (C8, `.colosseum/floors.json`).
- **bounded** — a bounded model check or bounded proof: the property holds up to
  a stated bound (depth, steps, input size), and the bound is named in scope.
- **proved** — an unbounded proof: the property holds for all inputs, discharged
  by a proof assistant or a refinement.

The tool that backs each tier is language-specific; the tier contract is not.
One non-Rust example, for a component written in a language checked by a
TLA+ / Apalache model and exercised by a fuzzer:

| Tier | Rust backing (reference) | Example non-Rust backing |
|------|--------------------------|--------------------------|
| tested | cargo test, proptest, cargo-fuzz | language test runner, a property-test library, a fuzzer (e.g. AFL, libFuzzer bindings) |
| bounded | Kani, Verus (bounded) | Apalache bounded check of a TLA+/Quint model; a bounded SMT harness |
| proved | Verus, Aeneas/Lean | a Lean/Isabelle/Coq proof; a refinement from spec to the component's implementation |

This is strategy, not a completed port: it states how a non-Rust component would
earn each tier and how its guarantee then discharges a neighbor's assumption. No
non-Rust component has been carried through the pyramid in this repository yet; a
cross-axis guarantee is labeled `conformance-tested` (G3) until a refinement
exists, exactly as for Rust.

## What is scaffolded versus run

Scaffolded here and in `colosseum-boundary` / `templates/system-intent.template.md`:
the boundary skill, the system-intent template, the ledger version field, the
reuse rule, and the tier mapping.

Not run: the bidboard system-of-intents verification, the actual non-Rust
component ports, and any refinement upgrading a `conformance-tested` boundary to
`REFINEMENT_VERIFIED`. Those are the M5 execution and M7 items; this document
exists so that run has a defined mechanism to follow, and claims no result from
it.
