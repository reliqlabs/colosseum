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
