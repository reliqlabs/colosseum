---
name: colosseum-lifecycle-adversary
description: Red-team multi-tx admin lifecycle features (Propose/Finalize/Cancel patterns, timelocks, state archival, multi-block sequences). Triggered by any change that adds or modifies an admin transition combining with existing protocol transitions. Extends the Quint protocol model to encode the new transitions, then generates adversarial counterexample traces against active-phase invariants over all multi-block sequences combining new admin transitions with existing ones. Use whenever a contract revision adds multi-step admin features (any Propose/Finalize/Cancel cluster, any timelock, any state archival path).
---

You are red-teaming a multi-tx admin lifecycle. A contract grew a feature with more than one admin transition (Propose + Finalize + Cancel; ProposeUpgrade + FinalizeUpgrade; ArchiveAndReset; or any multi-step admin lifecycle around state rotation). The naive flow lands the feature, updates the unit tests, and ships. The methodology's existing stages do not by themselves catch attack classes that combine the *new* admin transitions with the *existing* protocol transitions in adversarial sequences.

This skill is the missing stage. You extend the Quint model to encode the new transitions, then drive Quint-adversarial trace generation against active-phase invariants over all multi-block sequences. The output is a list of admissible attack traces with a verdict per trace.

## When this skill triggers

This skill is mandatory whenever a contract revision adds:

- **A new admin transition** that touches state read by other protocol transitions
- **A timelock** (any deferred-execution path where Propose-now / Finalize-later admits state changes between the two)
- **A multi-tx Propose/Finalize/Cancel cluster** (any feature where one tx records a pending change and a later tx commits or aborts it)
- **A state archival** (any path that moves "live" state into an "archived" map; the archival itself is an admin transition)
- **A registry-rotation feature** (the canonical case — a new pubkey/image/parameter overlays the old one through a multi-step process)

The trigger is structural, not severity-based. Even a "small" timelock that touches one field qualifies. The cost of running the skill is small; the cost of skipping it on a real feature can be a Major attack class.

## Why this exists

A real example: verified-rcv added a registry-rotation timelock (`ProposeRegistryUpdate`, `FinalizeRegistryUpdate`, `CancelRegistryUpdate`). The Quint protocol model was NOT extended when the three new transitions landed. No methodology stage red-teamed multi-block admin sequences combining the new transitions with the existing election-lifecycle transitions (`CreateElection`, `SubmitBallot`, `Resolve`). The external auditor found the trace `[CreateElection, ..., ProposeRegistryUpdate, ..., FinalizeRegistryUpdate]` reaching a DoS state — an in-flight election's encryption pubkey gets rotated out from under it. Major finding.

A lifecycle-adversary pass extending Quint at the same time as the feature landed would have produced this trace mechanically. The Quint model would have stated B1's active-phase invariant ("an in-flight election's encryption parameters are stable"), and the trace generator would have produced the counterexample. The bug surfaces in Quint counterexample format, not in audit-finding format, before any external audit.

## Step 1: Locate the artifacts

Ask the user for, or determine from context:

- **Project root** — absolute path.
- **Quint spec root** — usually `<project>/specs/<name>.qnt`. Required.
- **Intent document** — usually `<project>/.colosseum/intent.md`. Required.
- **The triggering commit / change record** — the commit or change-record path that introduced the multi-tx admin feature. Required input.
- **Code root for the new feature** — typically `<project>/crates/contract/src/`. Used to confirm the transition signatures the Quint model must mirror.

If the project has no Quint spec, stop. This skill operates on a Quint model; if there isn't one, you need `colosseum-intent` / `colosseum-compose` to produce one first. Lifecycle-adversary without Quint is hand-waved trace enumeration — too easy to miss interleavings.

## Step 2: Enumerate the new admin transitions

From the triggering commit, list every new admin transition the feature introduces. For each:

- Transition name (matching the contract's `ExecuteMsg` variant or equivalent)
- Inputs (who supplies them — admin, governance, time-based trigger)
- Preconditions (what state must hold for the transition to be admissible)
- Post-state effect (what state the transition writes; which fields, which Maps/Items)
- Multi-tx dependence: does this transition rely on a *prior* admin tx having landed? (Propose → Finalize pattern)
- Time dependence: does this transition rely on block-height or block-time gating?

Produce a transition table:

| Transition | Inputs | Preconditions | Post-state effect | Depends on | Time-gated |
|---|---|---|---|---|---|
| `ProposeRegistryUpdate { new_registry }` | admin | none | writes `PENDING_REGISTRY = (new_registry, now+TIMELOCK)` | — | no |
| `FinalizeRegistryUpdate {}` | admin | `PENDING_REGISTRY` set, `now >= PENDING_REGISTRY.unlock_at` | overwrites `REGISTRY = PENDING_REGISTRY.new_registry`; clears `PENDING_REGISTRY` | `ProposeRegistryUpdate` | yes |
| `CancelRegistryUpdate {}` | admin | `PENDING_REGISTRY` set | clears `PENDING_REGISTRY` | `ProposeRegistryUpdate` | no |

## Step 3: Extend the Quint model

Add each new transition as a Quint action in the spec file. The extension is mechanical when the transition table is honest:

```quint
action propose_registry_update(new_registry) = all {
  is_admin(sender),
  not(PENDING_REGISTRY.present),
  PENDING_REGISTRY' = Some({ new_registry: new_registry, unlock_at: now + TIMELOCK }),
}

action finalize_registry_update() = all {
  is_admin(sender),
  PENDING_REGISTRY.present,
  now >= PENDING_REGISTRY.value.unlock_at,
  REGISTRY' = PENDING_REGISTRY.value.new_registry,
  PENDING_REGISTRY' = None,
}

action cancel_registry_update() = all {
  is_admin(sender),
  PENDING_REGISTRY.present,
  PENDING_REGISTRY' = None,
}
```

Then extend the spec's top-level `step` or `init`+`step` disjunction to include the new actions:

```quint
action step = any {
  // existing transitions
  ...
  propose_registry_update(...),
  finalize_registry_update(),
  cancel_registry_update(),
}
```

Run `quint typecheck` to confirm the extended spec types.

## Step 4: Identify active-phase invariants the new transitions might violate

Walk the spec's `invariant` declarations and intent §3.2 (B-clauses) for properties that:

- Reference state the new transitions write
- Reference state the new transitions clear or rotate
- Reference state that depends on time-gated transitions (block-height monotonicity, deadline-based phases)
- Encode an "in-flight" or "active-phase" contract — properties that hold while a protocol instance is mid-flight (e.g., "an election's encryption parameters are stable while ballots are accepted")

Produce an invariant target list:

| Invariant | Statement | Why this transition might violate it |
|---|---|---|
| `inv_active_election_params_stable` | for any election in `ACTIVE` phase, the encryption pubkey at submit-time equals the pubkey at resolve-time | `FinalizeRegistryUpdate` rotates `REGISTRY.pubkey` and can fire mid-election |
| `inv_pending_registry_admin_gated` | `PENDING_REGISTRY` writes happen only via admin tx | not at risk — listed for completeness |

The list does not need to be exhaustive across all spec invariants; focus on the cross-section between "active-phase invariants" and "state touched by the new transitions".

## Step 5: Generate adversarial counterexample traces

For each target invariant, generate a trace using Quint's counterexample generator:

```bash
quint run --invariant inv_active_election_params_stable specs/<name>.qnt
```

For each trace produced:

- Capture the trace as a sequence of `(action, args)` pairs
- Note the trace length (number of transitions) and the violation point (which transition fired the violation)
- Note any "admin"-vs-"user" distinction in the trace's actors
- Determine which existing transitions interleave with which new transitions to produce the violation

If `quint run` cannot find a counterexample within its bound (typically 10 or 20 steps), document the absence explicitly — DO NOT silently move on. An invariant that survives a bounded check is informative; an invariant whose check timed out is differently informative.

Produce a trace table:

| Target invariant | Counterexample found? | Trace length | Violation point | Trace summary |
|---|---|---|---|---|
| `inv_active_election_params_stable` | yes | 4 | step 4 (`FinalizeRegistryUpdate`) | `[CreateElection, ProposeRegistryUpdate, AdvanceTime, FinalizeRegistryUpdate]` rotates pubkey while election is `ACTIVE` |
| `inv_pending_registry_admin_gated` | no (bounded) | bound=10 | — | held under 10-step bound |

## Step 6: Cross-reference traces to code enforcement

For each found counterexample, locate the code that should enforce the invariant. Three cases:

- **Code enforces the invariant; Quint missed the enforcement.** The Quint model is under-specified. Fix the Quint model (add the precondition that the code actually checks), re-run.
- **Code does NOT enforce the invariant; the bug is real.** This is a finding for the methodology stack — feed it to `colosseum-code-adversarial` as a known target, or surface directly as a bug to fix.
- **Code enforces the invariant but via a downstream layer the Quint model does not see** (e.g., the chain rejects the tx because of a different invariant). Document the cross-layer dependence; consider extending the Quint model to make it explicit.

Produce a verdict table:

| Trace | Code enforcement? | Verdict |
|---|---|---|
| `[CreateElection, ProposeRegistryUpdate, AdvanceTime, FinalizeRegistryUpdate]` | `FinalizeRegistryUpdate` handler at `crates/contract/src/handle.rs:412` has NO check that no election is mid-flight | bug — `FinalizeRegistryUpdate` must reject when any election is in `ACTIVE` phase |

## Step 7: Persist the deliverable

Write to `<project>/.colosseum/lifecycle-adversary/<feature-name>-<ISO-date>.md`. Format:

```markdown
# Lifecycle-adversary review: <feature-name>  —  <ISO-date>

- Triggering commit: <git rev>
- Triggering change record: <path or "n/a">
- Quint spec extended: <path>:<line-range of new actions>
- Active-phase invariants targeted: <N>
- Counterexamples found: <N>

## Transition table (Step 2)

<table>

## Quint extension diff

<unified-diff or per-action listing>

## Target invariants (Step 4)

<table>

## Counterexample traces (Step 5)

<table>

## Code-enforcement cross-reference (Step 6)

<table>

## Findings

| ID | Severity | Trace | Code site | Fix recommendation |
|---|---|---|---|---|
| LA-01 | Major | `[CreateElection, ProposeRegistryUpdate, AdvanceTime, FinalizeRegistryUpdate]` | `crates/contract/src/handle.rs:412` | reject `FinalizeRegistryUpdate` when any election is in `ACTIVE` |

## Summary

- Findings: <N> (<severity breakdown>)
- Recommended next step: revise code per fix recommendations; re-run after each fix; close lifecycle-adversary round when all counterexamples are eliminated (either by Quint-model precondition tightening that mirrors a code-side fix, or by Quint-model correction)
```

## Step 8: Report to the user

After persisting, report:

- One-line summary: `Lifecycle-adversary on <feature-name>: extended Quint with N transitions; targeted M active-phase invariants; found K counterexample traces; J counted as code bugs.`
- Absolute path to the deliverable
- The most severe finding's trace, in one line, as a sample
- Recommended next step: triage findings into the standard fix loop (`colosseum-change` from Step 5)

## Worked example: registry-rotation timelock

A real Quartz-family project added a registry-rotation timelock feature with three new admin transitions. A lifecycle-adversary pass run at that landing would have:

1. (Step 2) Enumerated `ProposeRegistryUpdate`, `FinalizeRegistryUpdate`, `CancelRegistryUpdate`.
2. (Step 3) Extended Quint's `specs/rcv.qnt` with the three new actions.
3. (Step 4) Identified `inv_active_election_params_stable` as a target invariant — the active-election encryption pubkey lives in `REGISTRY` and `FinalizeRegistryUpdate` rotates `REGISTRY`.
4. (Step 5) `quint run --invariant inv_active_election_params_stable` would have produced the trace `[CreateElection { id: 0 }, ProposeRegistryUpdate { new_registry: r' }, AdvanceTime(TIMELOCK), FinalizeRegistryUpdate {}]` violating the invariant at step 4.
5. (Step 6) The contract code at `crates/contract/src/handle.rs:412` (`FinalizeRegistryUpdate` handler) had no in-flight-election check. Verdict: bug.
6. (Step 7) Deliverable surfaces the bug in lifecycle-adversary format before an external auditor finds it.

The cost of the skill at feature landing: ~30 min wall-clock (Quint extension + 3-invariant counterexample run). The cost without it: one Major finding cascading into an external audit round.

## When to invoke

- Immediately after a commit lands a feature matching any trigger in "When this skill triggers" above
- During `colosseum-change` Step 4 (spec revisions) when the change adds new transitions
- After a Quint model is first written for a project that already has multi-tx admin features (catch-up application)

## Acceptance criteria

- Every new admin transition appears in the extended Quint model with explicit preconditions and post-state effects
- At least one active-phase invariant is targeted per new transition (or "no active-phase invariant interacts" is justified explicitly)
- Every target invariant has either a counterexample trace OR a bounded-check pass with the bound recorded
- Every counterexample is cross-referenced to code enforcement (Step 6 verdict)
- The deliverable file exists at the canonical path under `<project>/.colosseum/lifecycle-adversary/`

## Output deliverable

`<project>/.colosseum/lifecycle-adversary/<feature-name>-<ISO-date>.md` per the Step 7 format.

## What you do not do

- You do not edit code in this stage. Findings name the fix; you do not apply it.
- You do not skip Step 5's bounded check. "I read the spec and it looks fine" is not a substitute for `quint run`.
- You do not extend the Quint model in a way that bakes the contract's bugs into the model (Step 3 must mirror the contract's *intended* preconditions, not the buggy code's actual preconditions). If the contract is buggy and the Quint extension mirrors the bug, the counterexample disappears, and the skill defeats its own purpose.
- You do not declare an invariant "survived" because `quint run` hit a step-bound. Document the bound explicitly; a higher-bound run may produce a counterexample.

## Spirit

Multi-tx admin features grow the protocol's state space combinatorially. Hand-reasoning about all possible interleavings of N existing transitions × M new transitions is unreliable past a small N+M. Quint's bounded-model check is the right tool to enumerate the interleavings mechanically. The skill's job is to make sure that, every time the protocol gains a new transition, the model checker actually runs against the cross-product. Without it, attack classes that combine new and old transitions ship silently and surface during external audit; with it, they surface mechanically at the same time as the feature lands.
