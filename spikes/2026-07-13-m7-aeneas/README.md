# M7: Aeneas extraction + refinement proof over the jobq model

Artifacts for roadmap W5 (M7 refinement proofs). Started 2026-07-13 as a
feasibility spike; the refinement proof was COMPLETED 2026-07-14. NOT wired
into CI: these files build against an external toolchain (Charon 0.1.191,
Aeneas e8bd9d0b, the Aeneas Lean stdlib pinned to Lean v4.30.0-rc2 +
mathlib, whereas the repo BOM pins Lean 4.29.0). `repro.sh` regenerates and
typechecks the full chain from a clean state given those tools. Treat this
directory as recorded provenance, not as evidence the repo's gates consume.

## The result (2026-07-14): jobq code refines its spec, forward direction

`JobqRefinement.lean` proves that the Aeneas-extracted jobq model refines
the strengthened Quint transition relation (`specs/jobq.qnt`, module jobqP
at CAPACITY=2), so the model-checked invariants transfer to the actual
extracted code. 18 theorems, sorry-free, every one auditing to
`[propext, Classical.choice, Quot.sound]` (independently re-verified from
clean: recompile exit 0, `#print axioms` on all five transfer theorems).

- `QState`/`QStep`/`QInit`/`QReach`: a Lean transcription of the five jobqP
  actions and their guards; the five spec invariants (b1, b2 conservation,
  b3 biconditional, b4, nonneg) are proved INDUCTIVE over `QStep`, so the
  transfer rests on the Lean induction, not on Apalache's bounded run.
- `R`: field-wise `U32.val`-as-Int equality, capacity pinned to 2.
- init + per-action forward-simulation lemmas (submit/start/complete/fail,
  fail covering both retry and exhausted branches); `rust_refines_spec`
  then gives `rust_b1/b2/b3/b4` unconditionally over every reachable
  extracted state. `NonVacuity.lean` exhibits a concrete run reaching
  done=1, so the transfer theorems do not quantify over an empty set.
- Technique: `UScalar.add_equiv`/`sub_equiv` (ok-conditioned) rather than
  `add_spec`, so the unbounded `submitted` counter needs no boundedness
  hypothesis (a successful return already witnesses no overflow).

### Scope of the claim (what is NOT proved)

- Totality/progress (op succeeds whenever the spec guard holds): false at
  u32::MAX; this is exactly adjudication finding F2, left OPEN by design.
- Two-sided refinement (every spec step realizable by code): not attempted.
- Capacities other than 2 (kani separately covers 1..4 on the code side).

So any emitted label must be scoped, e.g.
`REFINEMENT_VERIFIED[forward, CAPACITY=2, ok-conditioned, finite-arith
excluded per F2]`. An unscoped label would overclaim. See the ROADMAP:
building the emission path is gated on a Quint-line citation binding,
because the `QStep` transcription is hand-written with nothing yet
mechanically binding it to `jobq.qnt`.

## Feasibility spike (2026-07-13), superseded by the result above

## What was established

- `tests/fixtures/r22/project` extracts cleanly with ZERO crate changes:
  `charon cargo --preset=aeneas` then `aeneas` produce `Jobq.lean`
  (33 items; the `#[cfg(kani)]`/`#[cfg(test)]` modules are inert under a
  normal charon build).
- The extracted model typechecks.
- `JobqProofs.lean` proves B1 over the extracted `fail`:

      theorem fail_preserves_b1 :
        attempts ≤ 3 is preserved by every ok-returning fail call

  Sorry-free; `#print axioms` reports only propext, Classical.choice,
  Quot.sound. The statement is conditional on the well-formedness bound
  because `fail` can overflow on the `failed + 1` path; totality past
  u32::MAX is not claimed (matching the panel's int-vs-u32 finding).

## What a real M7 refinement still needs (from the spike assessment)

Manual Quint-to-Lean transcription of `specs/jobq.qnt` (~8 defs), a
refinement relation bridging int/U32 and constant/field capacity (~2 defs),
init + per-action forward-simulation lemmas (~8-10), and for a two-sided
claim, reverse simulation + guard alignment (~10 more). An explicit
u32-boundedness hypothesis must live in the refinement relation. Risk to
manage: the hand transcription can drift from jobq.qnt silently; a
Quint-line citation gate analogous to the code ledger is wanted before the
label REFINEMENT_VERIFIED is ever emitted.

Toolchain locations are recorded in the project memory note
`m7-aeneas-toolchain` and in `repro.sh`.
