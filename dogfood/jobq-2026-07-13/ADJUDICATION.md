# Adjudication record: jobq panel attack, 2026-07-13

G4 adjudication of a real adversarial pass against the `tests/fixtures/r22/`
reference project (`jobq`). This is the exit-criterion-7 artifact: the
critique loop exercised on a real target, with the disposition governed by
evidence, not by vote count.

## Run

- Target: `jobq` INTENT.md + `specs/jobq.qnt`, the committed R22 fixture.
- Panel: `gpt-5.6-sol` and `glm-5.2` via OpenCode under the deny-first
  `spec-adversary` profile (reports in `reports/`); `kimi-k2.6` read the
  target but returned no report (gateway cutoff); `claude-agent` not run
  this pass. Two independent frontier reports is enough for adjudication.
- Both voices returned VERDICT: BREAKS with grounded, cross-cited findings.

## G4 stance

Evidence closes a finding; votes only triage. A finding two voices agree on
is not thereby true, and a finding one voice raises is not thereby false.
Each item below is dispositioned on its own evidence. Contested items stay
open with their hypothesis and the evidence retained.

## Findings

### F1. Invariants are weaker than the intent (`inv_b1` upper-bound only) — CONFIRMED, resolution pending

Both voices, independently. `inv_b1 = attempts <= MAX_ATTEMPTS` is necessary
but not sufficient for INTENT B1's "there is no fourth attempt." glm-5.2's
concrete trace: were `start` to set `attempts' = 0`, the machine would run
four `fail` calls (attempts 0->1->2->3) while `attempts <= 3` held at every
state, so `quint verify --invariant=inv_all` would pass a four-attempt
regime. The spec's own `start` sets `attempts' = 1`, so the current spec is
correct; the defect is evidentiary: the invariant set does not pin the
property down, so a future weakening of `start` would not be caught. This is
exactly the failure class E3/R9 exists to prevent, found in our own fixture.

Disposition: CONFIRMED as a genuine spec-quality gap. Closable by evidence:
add `inv_b1_lower = running implies attempts >= 1` (equivalently strengthen
`inv_b3` to a biconditional) plus a non-negativity invariant, and re-verify.
Not closed in this record; tracked as ROADMAP follow-up so the reference
project's own strengthening is itself a dogfood observation.

### F2. Conservation proven over unbounded `int`, code is `u32` — CONTESTED, OPEN

Both voices (gpt-5.6-sol "refinement mismatch", glm-5.2 "composition
failure"). The Quint counters are unbounded `int`; the Rust counters are
`u32`. `quint verify` establishes B2 conservation and terminal-count
monotonicity over unbounded integers, which does not by itself establish
them for the finite-width implementation: at `u32::MAX` submissions the
release build wraps and the debug build panics mid-mutation, either of which
breaks B2 for the real code.

Independent corroboration from a different axis: the W5 Aeneas extraction
spike (`docs/m7-feasibility.md`) proved B1 over the extracted `fail` only
for successful (`ok`) results, precisely because the extracted `fail` can
itself overflow on the `failed + 1` path. Two unrelated tools (a Quint-axis
adversary and a Lean-axis extraction proof) surfaced the same finite-arith
gap, which raises confidence the finding is real rather than an artifact of
one reviewer's framing.

Why it stays OPEN (contested, not closed): the two defensible readings do
not close on the evidence in hand.
- Defect reading: the intent states no submission bound, so the spec should
  model finite arithmetic (checked/saturating increments and their error or
  panic ordering) before B2 can be claimed for the code.
- Accepted-abstraction reading: an implicit operating bound (submissions far
  below `u32::MAX`) makes the unbounded-int model a sound abstraction, and
  the intent should record that bound as a trust assumption rather than the
  spec model the overflow.
Closing it needs new evidence, not a tally: either add checked arithmetic
plus a Quint model of the finite-width behavior, or add and justify a trust
assumption bounding total submissions. Per G4 the finding is retained OPEN
until one of those lands. Recording it as "resolved because two-of-two
voices flagged it" or "dismissed because it is unlikely in practice" would
both be the vote-closes-evidence error G4 forbids.

### F3. Spec fixes `CAPACITY = 3` while the code parameterizes capacity — CONFIRMED

Both voices. `specs/jobq.qnt` pins `CAPACITY = 3` and its comment claims it
"Mirrors src/queue.rs," but `JobQueue::new(capacity: u32)` is parameterized,
so `inv_b4` covers only the capacity-3 instance of a parameterized machine
(the kani harness covers 1..4, a different and also-partial domain).

Disposition: CONFIRMED scope limitation of the fixture. Honest to record:
R22 demonstrates the pipeline end to end on one capacity, not across the
parameter space. Resolution (parameterize the Quint module) tracked as a
ROADMAP follow-up; it does not weaken R22's gate-localization purpose.

## Outcome

Criterion 7 satisfied: the critique loop ran on a real target and produced a
genuinely contested finding (F2) that is retained OPEN under G4 rather than
closed by agreement, alongside confirmed spec-quality findings (F1, F3)
whose resolution is evidence-defined and tracked. The panel found real
weaknesses in our own reference project, which is dogfooding working as
intended. Follow-ups are in ROADMAP.md under "jobq spec strengthening."

## Addendum (same day, late-arriving evidence)

The run section above understates the panel: `kimi-k2.6`'s first dispatch
was killed by a 600s timeout, and the `claude-agent` seat HAD run (a fresh
`colosseum-spec-adversary` subagent on Fable 5) but its report reached the
orchestrator after this record was committed. Both reports are now in
`reports/` (kimi via a 900s retry). All four canonical-4 seats therefore
reported, all four with VERDICT: BREAKS. New evidence is dispositioned
here; nothing above is rewritten.

### Corroborations of existing findings

- F1: claude-agent #6 independently derives the inv_b3 vacuity half of F1's
  fix. Third voice.
- F2: claude-agent #8 adds the third independent axis (spec int totality vs
  u32 partiality with the debug-panic/release-wrap split). kimi #5 flags
  the same unbounded-int modeling from the non-negativity side. F2 REMAINS
  OPEN; the closing options are unchanged.
- F3: kimi #1 makes it four-of-four voices on the pinned CAPACITY.
  claude-agent #3 sharpens the disposition: the Quint artifact and the kani
  harness prove NON-EQUIVALENT theorems (capacity=3 vs capacity in [1,4]),
  and the spec cannot replay the fixture's own `new(4)`/`new(1)` unit
  tests. kimi #4 (capacity=0 unverified by any artifact) folds into the
  same parameterization fix.

### New findings

### F4. Terminal-count monotonicity is unencoded — CONFIRMED (executable evidence)

claude-agent #1 demonstrates it with a passing mutant: a `clawback` action
that decrements `failed` and `submitted` together conserves `inv_b2` and
passes `quint verify --invariant=inv_all` clean, while violating INTENT
line 43 ("counts only ever increase"). glm-5.2 #5/#6 and kimi #2 raised the
same gap declaratively. Quint state invariants cannot express a transition
property; the fix is a ghost-variable encoding (prev-counters carried in
state, invariant `done >= prev_done and failed >= prev_failed`) per the
quint-spec-generator ghost pattern, or action-level postcondition checks.
Tracked in the ROADMAP follow-up list.

### F5. Error outcomes are unobservable to the spec and the conformance bridge — CONFIRMED (scope limitation)

Raised independently by gpt-5.6-sol #2 (serious), claude-agent #5
(serious), kimi #3 (serious), glm-5.2 #8 (cosmetic; severity disagreement
noted, resolved toward serious on the evidence that INTENT B4 NAMES the
error value, so the spec under-specifies its own contract). The scalar
state carries no outcome datum, so a state-only replay cannot distinguish
`Full` from `NotRunning`. Resolution options: an `outcome` state variable
(ITF v1 already supports declared OUT tokens in the replay protocol), or an
INTENT edit scoping error-value conformance out. One must land; tracked.

### F6. Equal operator constants mask reference confusion — CONFIRMED (executable evidence)

claude-agent #2, unique to that voice: with CAPACITY == MAX_ATTEMPTS == 3,
swapping the constants in the submit guard and inv_b4 still verifies clean,
so a live guard/invariant mix-up is invisible to the model checker. Cheap
fix with outsized value: distinct constants (CAPACITY=2, MAX_ATTEMPTS=3) so
every reference discriminates. Tracked.

### F7. The witness set is asymmetric: no failed-path reachability witness — CONFIRMED

claude-agent #4: the only witness is `done > 0`; B1's defining outcome (a
job permanently failing after the third attempt) has no `failed > 0`
witness, so an edit making `fail_final` unreachable keeps `inv_all` green.
Fix: `witness_b1_failed = failed > 0` (and ideally a full-retry-chain
witness), added to the obligations manifest as a required target. Tracked.

### F8. "Missing obligations.json / ITF adapter" — REFUTED (environment artifact), with a confirmed residue

claude-agent #7 and kimi's glob both found no `.colosseum/obligations.json`
and no adapter. Both are artifacts of the attack environment: the dispatch
copy contained only INTENT.md, specs/, src/, and Cargo.toml. In the real
fixture both exist (`tests/fixtures/r22/project/.colosseum/obligations.json`,
`tests/fixtures/r22/adapter/`), are exercised by
`tests/r22_reference_project.py`, and Gate A/B run against them in CI. The
finding as stated is closed by that evidence. The residue is real and
CONFIRMED: the frozen manifest does not require the obligations F4 and F7
identify (no monotonicity target, no failed-path witness), so the
required-evidence set is weaker than the intent. That residue is exactly
F4/F7's fix path. Process note for future runs: attack copies should carry
the full project (or the report should name what was absent from scope) so
absence findings adjudicate cleanly.

### Outcome (addendum)

Unchanged: criterion 7 stands on F2 remaining OPEN under G4. The addendum
adds two executable-evidence findings (F4, F6), one four-voice confirmation
(F3), one severity-adjudicated scope limitation (F5), one asymmetric-witness
gap (F7), and one evidence-refuted finding with a confirmed residue (F8),
which together also exercise the refute-with-evidence arm of G4. Follow-ups
extended in ROADMAP.md.
