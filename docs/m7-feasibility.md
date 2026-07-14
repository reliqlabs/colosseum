# M7: Aeneas extraction + Lean refinement proof over jobq

Status: refinement PROVED, 2026-07-14 (feasibility spike 2026-07-13). The
extracted jobq model is proved to refine the Quint transition relation,
forward direction, at CAPACITY=2, so the model-checked invariants transfer
to the actual extracted code with a machine-checked, sorry-free proof. The
`REFINEMENT_VERIFIED` emission path is still NOT built (G3, R26): the
transcription of the spec into Lean is hand-written and nothing yet binds
it mechanically to `jobq.qnt`. The proof exists; the label is gated on a
Quint-line citation binding (see "Emission path" below).

## What ran

Against the `tests/fixtures/r22/` `jobq` crate, unmodified:

1. `charon cargo --preset=aeneas` produced `jobq.llbc` (LLBC frontend).
2. `aeneas -backend lean jobq.llbc` produced `Jobq.lean`, the extracted
   model of the queue operations.
3. A hand-written `JobqProofs.lean` proved, sorry-free, a bounded-retries
   theorem over the extracted `fail`:

   ```
   theorem fail_preserves_b1
       (self self' : queue.JobQueue) (o : ... FailOutcome QueueError)
       (hwf : self.attempts.val <= 3)
       (h : queue.JobQueue.fail self = ok (o, self')) :
       self'.attempts.val <= 3
   ```

4. `lean` typechecked both `Jobq.lean` and `JobqProofs.lean`; the `.olean`
   files are the evidence of a sorry-free, axiom-clean build.

The Lean source (`Jobq.lean`, `JobqProofs.lean`), the reproduction script,
and a not-in-CI note are committed under `spikes/2026-07-13-m7-aeneas/`. The
heavy build outputs (`.olean`, `.llbc`, `target/`) are not committed and
depend on locally-built Charon/Aeneas plus a prebuilt Aeneas Lean library;
toolchain paths are recorded in the `m7-aeneas-toolchain` memory. The build
reuses the `verified-rcv/specs` Lean environment (4.30.0-rc2) read-only,
which is ahead of the BOM pin (4.29.0); reconciling that pin is part of
closing M7.

## What this establishes and what it does not

- Establishes: the extraction toolchain works on a Colosseum fixture with no
  source edits, and a real behavioral clause (B1, bounded retries) is
  provable over the extracted code, machine-checked and sorry-free.
- Surfaced, independently of the panel: the extracted `fail` can overflow on
  the `failed + 1` path, so the theorem is stated over successful (`ok`)
  results only. This is the same finite-arithmetic gap the jobq panel raised
  (`dogfood/jobq-2026-07-13/ADJUDICATION.md`, F2), reached from a different
  tool. Two axes agreeing raises confidence the gap is real.
- Does NOT establish refinement: proving a property directly over the
  extracted model is the Aeneas/Lean exec-axis layer, not a proof that the
  extracted model refines the Quint transition relation. M7's
  `REFINEMENT_VERIFIED` bar requires the latter and remains unmet by design.

## The refinement proof (2026-07-14)

`JobqRefinement.lean` (18 theorems, sorry-free, standard axioms only)
closes steps 1-2 of the path below and carries the F2 bound as a stated
scope rather than resolving it:

1. `QState`/`QStep`/`QInit` transcribe the five jobqP actions and guards
   from `specs/jobq.qnt` into Lean; the five spec invariants (b1, b2
   conservation, b3 biconditional, b4, nonneg) are proved INDUCTIVE over
   `QStep`, so the transfer rests on a Lean induction rather than on
   Apalache's bounded run.
2. `R` is the field-wise `U32.val`-as-Int simulation relation, capacity
   pinned to 2. `init_sim` plus one forward-simulation lemma per action
   (submit/start/complete/fail, fail covering retry and exhausted
   branches) give `rust_refines_spec`; the transfers `rust_b1..b4` then
   hold unconditionally over every reachable extracted state.
   `NonVacuity.lean` exhibits a concrete run reaching done=1 so the
   transfers are not vacuous.
3. The finite-arithmetic gap (F2) is carried as scope, not resolved: the
   simulation lemmas use `UScalar.add_equiv`/`sub_equiv`, ok-conditioned,
   so a successful return witnesses no overflow. Totality at u32::MAX is
   NOT proved (it is false), matching F2, which stays OPEN.

Independently re-verified: recompiled from clean (exit 0, zero
sorry/native_decide/admit) and `#print axioms` on all five transfer
theorems returns `[propext, Classical.choice, Quot.sound]`.

### Emission path (still gated)

The proof is forward-direction only, CAPACITY=2, ok-conditioned, F2
excluded, and the `QStep` transcription is hand-written with nothing
mechanically binding it to the spec. So the honest label is scoped, e.g.
`REFINEMENT_VERIFIED[forward, CAPACITY=2, ok-conditioned, finite-arith
excluded per F2]`, and it is emitted NOWHERE until a Quint-line citation
gate (analogous to the code ledger's `@sha256` binding) ties each action
definition in `JobqRefinement.lean` to the action's line range in
`jobq.qnt`. Building that gate is the tracked ROADMAP item; the proof
artifact stands as recorded provenance in the meantime.
