---
name: colosseum-change
description: Change-loop for Colosseum-spec'd projects. Triages whether a proposed change is implementation-only or intent-touching, walks the user through the upstream-first revision sequence (intent → spec → code → verify → composition re-check), and produces a change impact report. Use whenever modifying a project whose existing trust artifacts the change might invalidate.
---

You are walking the user through a **change** to a system that already has Colosseum artifacts under it — intent doc, Quint specs, Lean theorems, Verus annotations, Kani harnesses, property tests, an integration ledger. Naive change ("just edit the code") risks silently invalidating verification artifacts: the build still passes, the tests still run, but the trust claims the project advertised no longer hold.

This skill is the disciplined change loop. It runs *before* code edits, then again after, with verification gates at each step.

## Why this skill exists

In a Colosseum-spec'd project, trust is composed across intent, specs, code, and proofs. A change can touch any layer and propagate. Without a structured loop:

- Code edits that violate the spec ship as long as nothing failed loudly enough
- Spec edits that no longer match intent become orphaned — formally proven but anchored to nothing
- Composition theorems silently lose nodes when an underlying artifact is renamed or removed
- The integration ledger drifts from the actual surface

The change loop is the methodology's answer to "what does it look like to maintain a Colosseum-spec'd project?"

## Your operating mode

You operate in seven steps. Step 1 (triage) is mandatory and short; it routes between the cheap path (implementation-only) and the full path (intent-touching). Subsequent steps are only run on the full path.

You guide; you do not auto-apply. The user is the decision-maker at each gate.

## Step 1: Triage — is this change intent-touching?

Ask the user to describe the change in one paragraph. Read the description and the surrounding artifacts. Decide:

**Implementation-only change** — the spec still holds, the change is a refactor, performance improvement, dependency upgrade, or internal restructuring that preserves observable behavior. Cheap path: skip to Step 6 (re-verify pyramid). The trust claims are unchanged; the proofs should still go through. If any proof fails after an implementation-only change, the change was *not* implementation-only — return to Step 1 with the new information.

**Intent-touching change** — the change alters observable behavior, error semantics, performance contract, trust boundaries, or invariants. Full path: continue to Step 2.

When unsure, default to full path. The cost of running it on a trivial change is small; the cost of skipping it on a non-trivial one is silent verification rot.

Output of triage:

```
Change classification: implementation-only | intent-touching
Reason: <one paragraph>
Affected surface: <module / function / spec list>
```

## Step 2: Intent revision

Edit `intent.md` to reflect the new behavior. Record the prior version in a revision-log section at the bottom of the document (or in a separate `intent-history.md` if the doc is short on space).

Do not delete sections silently. If a behavior is being removed, leave its description in place with a strikethrough or a `REMOVED in revision <N>:` marker so the diff is visible.

Then run `colosseum-adversarial` on the *diff*, not the new spec alone. The adversary's input is both the prior and new intent, framed as: "attack the delta — find a behavior that was correct under prior intent but is unspecified or contradicted under new intent, and vice versa."

If the adversarial pass surfaces issues, revise intent and re-attack until the diff survives. Only then proceed.

## Step 3: Impact analysis — which artifacts does the change touch?

Walk the project's verification surface and identify everything that references the changed behavior:

- **Quint invariants** that mention the affected state variables or action names
- **Lean theorems** whose statement or proof uses the affected definitions
- **Verus annotations** (`requires`, `ensures`, `spec fn`) that touch the changed function or its callers
- **Kani harnesses** that exercise the changed code path
- **Property tests** that assert on the changed behavior
- **Composition theorems** in the integration ledger whose dependency graph includes any of the above

Produce a checklist:

```
Affected by this change:
  Quint:   [ ] handshake.qnt:42 — inv_session_accepted_implies_vkey_set
           [ ] ...
  Lean:    [ ] Specs/Quartz/Protocol/Handshake.lean:64 — handshake_sound
           [ ] ...
  Verus:   [ ] crates/enclave/core/verus-prototype/key_manager.rs:96 — DefaultKeyManager invariant
           [ ] ...
  Kani:    [ ] src/state.rs:271 — session_with_pub_key_guards
           [ ] ...
  Tests:   [ ] tests/handshake_roundtrip.rs
  Compose: [ ] cross_component_session_bind  (composition theorem #3 in ledger)
```

The checklist is exhaustive. Missing an item here = a silent regression later.

## Step 4: Spec revisions — upstream-first

Revise specs in topological order — upstream first:

1. **Quint** if the change is protocol-shaped (touches the temporal structure)
2. **Lean** math / refinement specs if the change is reasoning-shaped (touches what is proved)
3. **Verus** annotations on Rust sources
4. **Kani harness signatures and bounds**
5. **Property test predicates**

After each tier, run `colosseum-adversarial` against the *newly revised* spec at that tier, then proceed downstream. This catches spec bugs before they propagate.

If a tier's spec depends on a not-yet-revised downstream tier (rare but happens — e.g., a Lean theorem about a Verus-annotated function), pause and ask the user to resolve the cycle. Cycles in spec dependencies almost always indicate a missing abstraction.

## Step 5: Code revisions

Now edit the Rust code. Bring the implementation in line with the revised specs.

Resist the temptation to edit code in parallel with specs — the discipline of upstream-first means the code edit becomes the *consequence* of the spec edit, not its driver. If during code editing you discover the spec is impossible to satisfy with reasonable code, return to Step 4 and revise the spec rather than weakening it silently in code.

### Companion-module pattern (for heavy-classpath verification scaffolding)

When a spec revision adds a verification library with a heavy transitive closure — VCV-io, ArkLib, mathlib subsets, large Verus prelude expansions — the naive integration imports the library directly into the affected spec file. This silently widens every downstream file's classpath and can blow `synthInstance.maxHeartbeats` (Lean) or push Verus past its solver budget on unrelated proofs.

The **companion-module pattern** is the disciplined alternative:

1. Keep the existing spec file's imports unchanged. Downstream files that synthesise instances against this module pay no cost.
2. Add a sibling file `<Module>Lift.lean` (or `<Module>VCVio.lean`, `<Module>Verified.lean` — choose a suffix that names *what the heavy import buys you*).
3. The companion module imports the heavy library and re-exposes the spec content in the heavier framework's idiom (OracleComp, AsymmEncAlg, refined Verus annotations, etc.).
4. Composition theorems that need the heavy framework import the companion, not the core spec.

Two health signals confirm the pattern is working:

- **Build cost is flat after the one-time classpath hit.** Adding the second companion module is +1 build job, not +N.
- **Downstream type-class synthesis paths are unaffected.** Re-run `colosseum-verify`; if downstream proofs that were green before the change are now stuck on instance synthesis, the pattern is being violated somewhere.

Use this pattern whenever the spec revision is *additive in expressive power but contagious in build cost*. It's the structural fix for the failure mode where adding a sound foundation breaks every unrelated proof in the project. (Recorded as a Quartz/VCVio finding — emerged across all five collection-phase steps of the Quartz refactor.)

## Step 6: Re-verify the pyramid

Run `colosseum-verify`. Expect two kinds of failure:

- **Intentional regressions** — proofs that should fail because the change deliberately removed a behavior. These are not bugs; they confirm the change took effect. Update or delete the affected proofs as appropriate.
- **Unintentional regressions** — proofs that fail because the change broke something the team did not mean to break. These are bugs in the change; classify via `colosseum-failure-classifier`.

Halt on any unintentional regression. The change is not complete until the pyramid is green at the new spec.

## Step 7: Composition re-check + ledger delta

Run `colosseum-compose` to regenerate the integration ledger. Compare to the prior ledger:

- **Composition theorems that disappeared** — every loss is a trust-claim retraction. The change description should state explicitly why each one is no longer needed (or, more often, that they need to be re-proven against the new specs).
- **Axioms that appeared** — every new axiom is a new trust claim. Each should have a justification line.
- **Coverage shifts** — surface them by number, not vibes.

The ledger delta is the artifact that goes in the PR description. A reviewer reads the delta and decides whether the change is acceptable from a verification standpoint.

## Step 8: Persist the change record

Write a change record to `<project>/.colosseum/changes/<ISO-timestamp>-<short-name>.md`:

```markdown
# Change record: <short name>

- Date: <ISO timestamp>
- Classification: implementation-only | intent-touching
- Intent revision: <none | new version <N>>
- Cycle-outcome intent: <one of the four enum values below — REQUIRED for any cycle that produces a `_negl` lift, optional otherwise>

## Description

<one paragraph from Step 1>

## Affected verification surface

<checklist from Step 3, with each item marked completed or NA>

## Adversarial review

<paths to adversarial reports against intent diff and each spec tier>

## Ledger delta

<diff against prior ledger — theorems / axioms added/removed, coverage shifts>

## Outstanding follow-ups

- <any unproven re-statements>
- <any new axioms needing justification>
- <any deferred work>
```

### Change-outcome intent enum

The `Change-outcome intent` field captures the intent behind a security-lift change's outcome. When the change's lifted advantage proves identically zero (`failAdv 𝒜 n = 0`), the change is *valid but underwhelming* — the conclusion follows unconditionally from the hypotheses, with no probabilistic-failure event. Without explicit declaration, auditors cannot distinguish intentional non-modelling from genuine vacuity.

The four enum values:

1. **`probabilistic-failure-modelled`** (default — the lift bounds a real probabilistic event with non-zero failure advantage). Most changes fall here.
2. **`degenerate-by-design — scope excludes the failure event`** (the spec is intentionally not modelling the relevant probabilistic phenomenon under the current carrier abstraction; e.g., Quartz's `session_confidentiality_negl` models deterministic correctness, not CPA security — IND-CPA is out of the current scope by design). A scope-bounded lift is honest within its scope.
3. **`degenerate-by-accident — abstraction collapsed the failure event`** (the lift is structurally trivial because the carrier model elided the event; a refactor is needed to restore it). This is a methodology obligation — the lift should not ship as a "security lemma" without the refactor.
4. **`follow-up to add it`** (the lift ships now as `degenerate-by-design` or `degenerate-by-accident`, with a tracked follow-up change queued to add the probabilistic claim later).

**Why this is enumerated, not free-form prose**: auditors can grep change records for `Change-outcome intent: degenerate-by-accident` and surface all instances at once. Free-form prose buries the audit signal. The discreteness IS the audit affordance.

The change record is the project's history of how its trust claims evolved. Treat it as load-bearing.

## What you do not do

- You do not skip Step 1. Even "obviously implementation-only" changes get triaged — the discipline is the value.
- You do not edit code before specs. Upstream-first or the spec drifts.
- You do not silently delete proofs that "no longer apply." Every removal is a trust-claim retraction; mark it visibly.
- You do not paper over an unintentional regression to ship the change. The regression is information about the change.
- You do not run this skill on a project that has no Colosseum artifacts. There is no spec'd project to maintain — start with `colosseum-intent` or `colosseum-reverse-intent` instead.

## Failure modes

- **The user wants to ship an unintentional regression as a known-acceptable risk.** This is a real choice; the ledger has to record it as a downgrade of the affected trust claim. Do not pretend the proof still holds. Mark the affected composition theorem as "downgraded — see change record <path>".
- **The change is too large for one loop.** Decompose. Sequence dependent changes through separate change records. The methodology rewards small, well-scoped changes; one giant change that touches the whole spec surface is unverifiable in practice.
- **The intent doc is missing.** Run `colosseum-reverse-intent` first. Then come back here.

## Spirit

A Colosseum-spec'd project has spent effort building trust artifacts. The cost of that effort is justified only if the artifacts stay aligned with the system as it evolves. Most verification methodologies are silent on change — they treat verification as a one-time event. Real systems change every day. The change loop is the methodology's answer to "how does verification survive ongoing development?" If the loop runs, the artifacts stay meaningful. If it doesn't, the project accumulates proofs about a system that no longer exists.
