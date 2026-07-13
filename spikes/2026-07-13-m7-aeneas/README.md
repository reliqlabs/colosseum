# M7 spike: Aeneas extraction + first proof over the jobq model (2026-07-13)

Feasibility artifacts for roadmap W5 (M7 refinement proofs). NOT wired into
CI: these files build against an external toolchain (Charon 0.1.191, Aeneas
e8bd9d0b, the Aeneas Lean stdlib pinned to Lean v4.30.0-rc2 + mathlib,
whereas the repo BOM pins Lean 4.29.0). `repro.sh` regenerates and
typechecks everything from a clean state given those tools. Treat this
directory as recorded provenance, not as evidence the repo's gates consume.

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
