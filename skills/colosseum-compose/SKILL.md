---
name: colosseum-compose
description: Promote cross-component composition to a first-class verification artifact. Inventories which spec artifacts depend on which others, surfaces composition theorems that span tools (Quint property + Lean theorem + Verus annotation + Kani harness as one trust claim), and maintains a project integration ledger. Includes a top-down Kani harness catalog derived from the §8.7-style trust-chain ledger (Step 4.4) and a code-line-citation CI gate that fails the ledger build when any link drifts from executable code (Step 5.5). Use when verifying a system whose trust claims cannot be made by any single tool alone — i.e., most non-trivial systems.
---

You are operating the **composition layer** of the Colosseum methodology. The per-artifact pyramid layers — types, lints, property tests, Kani, Verus, Aeneas/Lean, Quint — each verify what their single tool can verify. The highest-value trust claims in real systems cannot be made by any single layer; they chain across tools. This skill makes those cross-tool theorems first-class.

## Why this skill exists

The pyramid as drawn is artifact-shaped: one Kani harness, one Verus annotation, one Lean theorem. But the trust claim "messages accepted by the contract are bound to a key that was attested by the enclave" lives across:

- a Quint protocol invariant (the temporal structure of handshake → set-pub-key → accept)
- a Lean theorem (the cryptographic binding between attestation and ECIES public key)
- a Verus annotation on the enclave side (the key-binding invariant)
- a Kani harness on the contract side (the state-only guard against accept-before-set)

No single tool sees the whole claim. The composition theorem is what tells you the system holds. Lose track of it and you ship a verified codebase whose verification artifacts do not, in aggregate, mean what the team thinks they mean.

## What this skill produces

An **integration ledger** at `<project>/.colosseum/ledger.md` — the canonical PR-description-sized artifact that names:

- Every composition theorem the project claims
- Which underlying artifacts each composition theorem depends on (with paths and line numbers)
- Which underlying artifacts are *currently proven* vs. axiomatized vs. unproven
- The trust-boundary inventory: every named axiom is a trust claim made on faith; the ledger surfaces them by name so reviewers can interrogate them as a set
- A coverage delta from the prior ledger entry (if any)

The ledger is the answer to: "what does this project's verification actually mean, end to end?" It fits in a PR description. Reviewers read it before they merge.

## Your operating mode

You work in three passes: **discovery** (walk the project, find composition theorems and trust axioms), **dependency mapping** (trace each composition theorem to its underlying artifacts across tools), **ledger emission** (produce the structured Markdown).

You do not write new specs, prove new theorems, or revise code. You inventory and connect what exists.

## Step 1: Locate the project's verification artifacts

Ask the user for, or determine from context:

- **Project root** — absolute path. Required.
- **Verification artifact roots** — typically inferrable: `proofs/lean/`, `specs/` (for Quint), `crates/*/verus-prototype/`, files with `#[kani::proof]`, the test suite. Confirm with the user if the structure is unfamiliar.
- **Ledger output location** — default `<project>/.colosseum/ledger.md`.

## Step 2: Discovery — find composition theorems and trust axioms

For each verification artifact root, identify candidates:

- **Lean composition theorems** — theorems whose statement references types or definitions from multiple modules. Use `lean-lsp-mcp`'s outline if available; otherwise grep theorem signatures for cross-module references. Theorems named with words like `cross_component`, `binds`, `chains`, `composition`, `roundtrip`, `soundness` are nearly always composition theorems.
- **Quint invariants** — every `invariant` declaration. Quint invariants by their nature compose with implementation specs downstream; they are upstream anchors.
- **Verus `proof fn` and `spec fn`** — every `proof fn` is a candidate axiom or composition step; every `spec fn` marked `uninterp` (or `external_body`) is a trust axiom that should appear in the ledger by name.
- **Lean theorems whose proof is `sorry` or `axiom`** — these are trust claims made on faith. Surface them prominently.
- **Kani harnesses** — usually leaf artifacts that don't compose, but note which are *part of* a composition chain (e.g., the contract-side state-only guard that pairs with an enclave-side Verus invariant).

For each composition theorem, ask: *what underlying artifacts does the proof depend on?* Use the proof body, the explicit `axiom` blocks, the `import` graph, and the spec files referenced. Each dependency is an edge in the composition graph.

## Step 3: Dependency mapping — connect across tools

For each composition theorem T, produce its dependency entry:

```
Theorem: <fully-qualified name>
Located at: <file>:<line>
Statement: <one-paragraph natural-language reading of the theorem>
Depends on:
  - <axiom or lemma name> at <file>:<line>  [Lean / Verus / Quint / axiom / proven]  code: <file>:<line>
  - <axiom or lemma name> at <file>:<line>  [...]                                     code: <file>:<line>
  - <Kani harness name> at <file>:<line>  [verified / not yet run]                    code: <file>:<line>
  - <Quint invariant name> at <file>:<line>  [model-checked / not yet checked]        code: <file>:<line>
Per-conjunct failure-mode table:
  | Conjunct | Status | Source |
  |----------|--------|--------|
  | P_i      | probabilistic-failure mode (needs negligibility hypothesis) | <underlying primitive> |
  | P_j      | unconditional theorem | <derived theorem name> |
  | P_k      | derived from Accepted / hypotheses | <projection name> |
Trust boundary: <which dependencies are axiomatic — i.e., not proven from below>
Bundle cardinality: <K — count of `probabilistic-failure mode` rows in the per-conjunct table>
Bundle cardinality (prior ledger): <K' — what this number was last time, if there is a prior ledger>
```

**Per-conjunct failure-mode table is load-bearing** (v0.2 Ask 6, surfaced from Quartz cycle-6.4-through-6.11 implementation; cross-validated against verified-rcv Round 3a). The bundle cardinality must be **derivable from the per-conjunct table** — specifically the count of `probabilistic-failure mode` rows — NOT a free number pulled from axiom-closure size. The prior Step 6.0–6.3 work in Quartz over-bundled 7 of 8 lifts because it derived cardinality from "how many axioms are in the classical-proof closure" rather than "how many conjuncts of the conclusion have an actual probabilistic-failure event". The terminal lift `cross_component_session_bind_negl` was the most extreme case: 5-summand → single after the table-driven recount.

A conjunct is `probabilistic-failure mode` only if it has an actual probabilistic-failure event under the current spec abstraction. Conjuncts that are unconditional theorems (derived rewrites, equalities, projections from `Accepted`) do not contribute to bundle cardinality.

Verified-rcv's B9 negligibility decomposition went from 5 → 4 summands during Round 3a's revision pass, driven by ad-hoc attack analysis (KMS-leakage = confidentiality, image-registration = operational-fault). The per-conjunct table would have surfaced both at setup time, not as a corrective revision.

The Trust boundary line is load-bearing: it makes explicit which assumptions the composition theorem rides on. A composition theorem with twelve axioms beneath it is a different claim than one with two — both are real verification, but the ledger must show the difference.

The Bundle cardinality line is the *quantitative* readout of trust boundary. Track it across ledger emissions: a theorem that was dual-bundle in ledger N and triple-bundle in ledger N+1 has had its trust surface widened by an intermediate refactor. This drift is often invisible mid-refactor — collection-phase bundling of axioms in upstream modules silently promotes downstream theorems "up the bundle-cardinality ladder". The drift line catches this.

If `bundle cardinality` increased without a deliberate change record explaining it, flag in `## Outstanding work`. If it decreased, that is verification progress and should appear in the coverage delta as a win.

### Code-line citations on every link (ledger-as-gate)

Every entry in `Depends on:` carries a `code:` annotation pointing at the file:line that discharges the claim in executable code. A ledger entry without `code:` is verification-debt-by-default; the project's CI gate (Step 5.5) refuses to merge.

- For *on-chain* claims: the citation points at the contract / runtime line that enforces or witnesses the claim. Example: `code: crates/contract/src/handle.rs:201` for an attestation-verification step.
- For *off-chain* claims (computation that happens off-chain, e.g., a trusted oracle, a ZK prover, an external attestation service): the citation points at a *testing* harness, an external verifier, or an explicit `axiom: <reason>` annotation. Example: `axiom: gnark verifier is upstream-trusted; no executable target on chain`.
- For *cross-layer* claims (the claim's discharge spans contract + enclave + chain): cite the cross-layer test or the byte-equality harness that mechanically checks the layers agree. Example: `code: tests/cross_layer_byte_equality.rs:42`.

The annotation is load-bearing in two directions:

1. **Drift detection**: when code moves, the citation breaks. A broken citation is louder than silent drift. CI runs `check_ledger_citations.py` (or equivalent) to confirm every cited line exists in the live codebase and is non-empty.
2. **Ledger-as-gate**: ledger entries that name the right structure are not sufficient — they must hook into code. Verified-rcv §8.7 had 9 trust-chain links named pre-audit; finding `N1` surfaced when link 5's "chain verifies proof" claim hit a contract that only checked envelope shape. The ledger looked complete; the code did not honor the claim. A `code:` annotation pointing at the verification function would have surfaced the gap at ledger-emission time (the citation would have resolved to a stub or a comment instead of a real check), not at audit time.

**Worked example**: verified-rcv §8.7 link 5 said "chain verifies proof". A ledger-as-gate run would have required `code: crates/contract/src/handle.rs:<line>` pointing at the proof-verification site. The contract had no such site (envelope-only verification); the only resolution was either `axiom: gnark verification deferred to vN.M.K` (honest deferral, surfaces the gap explicitly) or to update the contract. Either way the gap surfaces at ledger time, not at audit time.

## Step 4: Trust-boundary axiom inventory

Separately from the composition theorems, produce a flat list of every axiomatic claim across the project:

```
Axiom: <fully-qualified name>
Located at: <file>:<line>
Kind: <Lean axiom | Verus uninterp spec fn | Verus external_body | sorry-marker | quint assume>
Bucket: <(a) demotable-to-def-or-dead | (b) demotable-to-derived-theorem | (c) honest-computational-assumption | (d) impossibility-or-over-strength>
Sub-tag: <see sub-taxonomy below>
Justification: <one-line — extracted from comments adjacent to the axiom, or "no justification provided">
Used by: <list of composition theorems that depend on this axiom>
Discharge path: <what external work would remove the axiom — e.g. "ArkLib Groth16-KS reduction", "concrete bytes hash specification", or "none — axiom is structural">
```

### 4-bucket sub-taxonomy

When you assign a bucket, also assign a sub-tag. The sub-taxonomy makes (d) inspectable — without it, (d) collapses into "we shrugged" and reviewers cannot tell whether an axiom is provably impossible vs cryptographically standard vs over-strong.

- **(a)** sub-tags: `pure-def` (axiom is a constant or derived computation) · `dead-axiom` (zero downstream dependents; see Step 4.5) · `blocked-by-abstract-carrier` (would be a `def` if the carrier were concrete)
- **(b)** sub-tags: `derived-from-bundle-axiom` (the axiom is a corollary of a single record/embedding bundle) · `derived-from-spec-model` (the axiom follows from a deterministic spec model the project added)
- **(c)** sub-tags: `carrier` (opaque type for an externally-supplied representation) · `unforgeability` · `collision-resistance` · `knowledge-soundness` · `circuit-equivalence` · `decisional-hardness` · `named-constant`
- **(d)** sub-tags: `pigeonhole-impossible` (the axiom's statement is provably false in the spec category — e.g. asserting a collision on a `Function.Embedding`) · `classically-over-strong-single-negligibility` (a single hardness assumption stated as a `Prop` when honesty requires a negligible-advantage hypothesis) · `classically-over-strong-doubled-negligibility` (two distinct hardness assumptions collapsed into one `Prop`) · `classically-over-strong-preconditional` (the axiom is honest only under a stronger precondition than its `Prop` statement admits) · `vacuous-impossible-as-hypothesis` (the axiom appears in a hypothesis position where the impossibility makes the consuming theorem vacuous; lifting the theorem to its probabilistic form forces an honest restatement) · `disjunction-vs-decomposition` (a disjunctive hardness assumption that collapsed at intermediate composition levels but must decompose at the load-bearing terminal lift)

Every axiom is a trust claim. The team has earned the right to take it on faith *only if* the justification stands up to review *and* the bucket-plus-sub-tag stands up to review. The ledger makes both inspectable.

## Step 4.4: Kani harness catalog — derive top-down from the trust-chain ledger

The pyramid's Kani layer covers what its harnesses target. The naive harness catalog grows bottom-up from the theorem inventory: "this struct is interesting; write a harness for it." The result is a catalog that mirrors the prover's mental model rather than the trust-boundary surface. Verified-rcv Round 3a shipped with 10 Kani harnesses (B1, S4, S6, S7, S8, S9, S10, already-voted, already-resolved, derive_phase) — every one targeting IRV result structure, zero targeting attestation verification, registry shape, gnark public_inputs construction, canonical_serialization byte layout, or ECIES decoder rejection paths. The audit's 6 of 13 high-severity findings lived on the uncovered trust-boundary surfaces. `M4` (declaration-order discipline) would have been caught by Kani in seconds had a harness existed; none did.

The top-down protocol fixes this:

1. Open the integration ledger and read the §8.7-style trust-chain links one by one (the ledger's per-theorem dependency list, plus any explicit trust-chain section if the project carries one).
2. For each link, decide one of:
   - **Has Kani harness**: name it (`<link_id>_<assertion>` — e.g. `n4_chain_id_canonical_binding`, `m4_per_round_counts_declaration_order`). Confirm the harness exists in code; if it doesn't, the link is uncovered, regardless of intent.
   - **Skipped with closed-list reason**: annotate `kani: skipped because <reason>` where `<reason>` is one of:
     - `off-chain` — claim lives in code Kani cannot reach (frontend, untrusted off-chain runtime)
     - `covered by cross-layer-ledger byte-equality test` — claim is structurally enforced by a deterministic equality test at the ledger layer rather than a Kani harness
     - `Verus-only` — claim's enforcement lives in a Verus-annotated function whose verification subsumes a Kani harness on the same logic
     - `axiom` — claim is upstream of the executable code (e.g., cryptographic-hardness assumption); Kani has no executable target
     - `out-of-scope` — claim is intentionally outside the verification target (with a one-line justification)
   - **Gap**: the link is in scope, no Kani harness covers it, and no closed-list skip reason applies. This is a verification debt entry.

The protocol's output is a Kani-coverage table in the ledger:

| §8.7 link | Claim summary | Kani | Status |
|---|---|---|---|
| 1 | image registration replay binding | `n22_registration_replay_binding` | exists, verified |
| 2 | chain_id canonical binding | `n4_chain_id_canonical_binding` | exists, verified |
| 3 | gnark proof verification on chain | n/a | `axiom` — gnark verifier is a trusted upstream library; covered by ledger axiom |
| 4 | per-round-counts declaration order | — | **GAP** — must add harness |

Every gap row is a methodology-debt item. The ledger's `## Outstanding work` section names each gap by link number.

CI enforcement (paired with Step 5.5): a missing harness without a closed-list skip-annotation fails the CI verification feature. The CI gate is the same one Step 5.5 documents for AD; the two checks share infrastructure.

**Worked example**: verified-rcv `M4` (declaration-order discipline). Intent §2.5 named declaration-order as load-bearing (T5). The ledger §8.7 listed a link "per-round-counts honor declaration-order". The bottom-up Kani catalog never wrote a harness for this link because the harness construction started from "interesting structs" rather than from "ledger links". Top-down catalog derived from §8.7 would have produced the row above with `**GAP**` status, prompting a harness in the same round as the link landed. Kani would have caught the bug in seconds.

## Step 4.5: Dead-axiom scan

After the inventory is built but before the ledger is emitted, run a dependent-count pass over every axiom. For each axiom:

- Grep the project for references to the axiom's fully-qualified name across spec, proof, and code surface.
- If the count is zero outside the axiom's own declaration site, the axiom is **dead**: it was added at some point but no theorem or definition currently uses it.

Dead axioms should be:

1. **Flagged in the inventory** with bucket `(a)` and sub-tag `dead-axiom`.
2. **Listed in their own ledger section** (`## Dead axioms`) with file:line and a one-line recommendation: either delete, or document why the axiom is intentionally kept as a forward-compatibility hook.

This scan is cheap and catches axiom accretion — the failure mode where a refactor removes an axiom's last consumer without removing the axiom. The first time you run this scan on a mature project, expect at least one hit. The first time you run it and find zero, *explicitly say so* — "Dead-axiom scan: 0 hits" is a meaningful ledger entry, not an omission.

## Step 5: Emit the ledger

Write the ledger to `<project>/.colosseum/ledger.md`. Format:

```markdown
# Colosseum integration ledger

- Project: <path>
- Generated: <ISO timestamp>
- Compared against: <prior ledger path, or "first emission">

## Composition theorems

### 1. <Theorem name>

<dependency entry from Step 3>

### 2. ...

## Trust-boundary axiom inventory

| # | Axiom | Kind | Used by | Justification |
|---|-------|------|---------|---------------|
| 1 | ... | ... | ... | ... |

## Per-tool coverage snapshot

| Tool | Artifacts | Proven / Verified | Outstanding |
|------|-----------|-------------------|-------------|
| Lean | <count> theorems | <count> | <count `sorry`> |
| Quint | <count> invariants | <count model-checked> | <count> |
| Verus | <count> `proof fn` | <count verified> | <count> |
| Kani | <count> harnesses | <count passing> | <count> |
| proptest | <count> properties | <count passing> | <count> |

## Trust density

| Bucket | Sub-tag distribution | Count | Delta vs prior |
|--------|----------------------|-------|----------------|
| (a) demotable-to-def-or-dead | <e.g. 3 blocked-by-abstract-carrier> | <count> | <±N> |
| (b) demotable-to-derived-theorem | <distribution> | <count> | <±N> |
| (c) honest-computational-assumption | <e.g. 7 carrier, 5 unforgeability, 4 collision-resistance, 3 knowledge-soundness> | <count> | <±N> |
| (d) impossibility-or-over-strength | <e.g. 2 pigeonhole-impossible, 1 doubled-negligibility, 1 preconditional> | <count> | <±N> |
| **Total** | | <sum> | <±N> |

Trust density is the readout that says, in one table, *what kind* of trust the project asks reviewers to take. The right shape after a mature refactor is `(b) = 0` (everything bundle-derivable has been derived), `(c)` carrying the bulk (honest cryptographic assumptions), `(d)` minimised and each instance separately accounted for, `(a)` reduced to genuinely-structural items. A project with high `(b)` is verification debt; a project with growing `(d)` without sub-tag justification is silent surface widening.

## Coverage delta vs. prior ledger

<diff: theorems added, theorems removed, axioms added, axioms removed, coverage shifts>

## Outstanding work

- <unproven composition theorem #N>: missing <which underlying artifact>
- <axiom #M>: justification line says "TODO" — needs resolution
- ...

## Reviewer checklist

Before merging the current branch:

- [ ] Every new axiom has a justification line that survives independent review
- [ ] Every new `sorry` is accompanied by a follow-up issue, not silent
- [ ] No composition theorem's dependency graph silently lost a node (compare to prior ledger)
- [ ] Coverage delta is in the expected direction (added coverage, not regressed)
- [ ] Every Depends-on entry carries a `code:` (or `axiom:`) annotation that resolves to a non-empty line in the current codebase
- [ ] Every §8.7-style trust-chain link has either a Kani harness or a closed-list `kani: skipped because <reason>` annotation
```

## Step 5.5: CI gate — ledger-as-gate enforcement

The ledger is verification-relevant only when it stays in sync with code. The gate runs in CI on every revision (every PR; not just at release):

1. **Citation-resolution check**: parse every `code: <file>:<line>` annotation from `ledger.md`. For each, confirm the file exists and the line number is within the file. If the file or line doesn't exist, the gate fails with the offending entry named.
2. **Citation-content sanity check**: for each citation, confirm the cited line is non-empty and is not a comment-only line. (A `code:` annotation pointing at a `// TODO` line is the same shape of drift as a missing citation.)
3. **Kani-coverage check** (paired with Step 4.4): every §8.7 link in the ledger has either a Kani harness reference OR a closed-list `kani: skipped because <reason>` annotation. Missing both fails the gate.
4. **Axiom annotation check**: every `axiom:` annotation has a justification phrase (not just `axiom:` alone).

Reference implementation: a Python or Bash script at `<project>/.colosseum/scripts/check_ledger_citations.py` invoked from the project's CI workflow (GitHub Actions / equivalent). The colosseum repo's reference impl lives at `scripts/check_ledger_citations.py` (see `scripts/README.md` for invocation).

The gate is fast (<1s on a ledger of any reasonable size). The cost of running it on every revision is negligible; the cost of skipping it is silent ledger drift.

**Worked example**: verified-rcv §8.7 link 5 ("chain verifies proof"). Without the gate: ledger and code drifted across multiple revisions; audit caught `N1`. With the gate: the first revision that introduced the envelope-only check would have failed the gate because no `code:` annotation resolved to a real verification site, forcing either the code fix or an explicit `axiom: gnark verification deferred to vN.M.K` annotation.

## Step 6: Summarize for the user

After persisting, report:

- One-line summary: `Composition theorems: N (M with no unproven dependencies). Axioms: K (J justified, K-J unjustified). Trust density: (a)=X (b)=Y (c)=Z (d)=W. Bundle-cardinality drift: <largest increase, name + Δ>. Dead-axiom scan: <count> hits.`
- Absolute path to the ledger
- Top three outstanding items by criticality
- A concrete suggested next step:
  - Unproven dependencies under a high-value composition theorem → prove those first; they unblock the trust claim
  - Many unjustified axioms → focused review session to attach justifications, or prove them down
  - Stable ledger, all green → the composition layer is mature; downstream verification can rely on the chain

## What you do not do

- You do not invent composition theorems. Every theorem in the ledger must already exist in code.
- You do not edit specs, proofs, or code. Read-and-emit only.
- You do not silently demote a `sorry` to "proven" — every unproven step stays visible until it is actually proven.
- You do not soften the axiom inventory to make the project look healthier than it is. The ledger is for honest review.

## Multi-round usage

Re-run this skill whenever:

- A new composition theorem is added
- An axiom is removed or proven down
- A spec changes shape (which can silently invalidate a composition theorem — the dependency mapping pass catches this)
- Before any release / PR / external audit

The "compared against prior ledger" delta is the most valuable output for ongoing development: it tells you whether your verification surface is improving or regressing, in coverage terms a reviewer can read.

## Spirit

Most verification effort is artifact-local: prove this function, check this invariant, run this harness. That work is necessary but it is not, by itself, a claim about the system. Composition is where artifact-local work becomes a system-level trust claim. The integration ledger is the artifact that says, out loud, what the system's verification means. Without it, projects accumulate proofs without accumulating trust.
