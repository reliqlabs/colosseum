# M7 feasibility: Aeneas extraction + Lean proof over jobq

Status: feasibility spike, 2026-07-13. Establishes that the proved-tier
exec-axis layer (Rust to Lean via Charon/Aeneas, then a machine-checked
theorem) is reachable for a real Colosseum reference project. It does NOT
yet close M7: no refinement of the extracted model against the Quint spec
has been proved, so `REFINEMENT_VERIFIED` is still emitted nowhere (G3, R26).

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

## Path to closing M7

1. State the refinement relation between `specs/jobq.qnt` and the extracted
   `Jobq.lean` explicitly (a simulation relation on the shared scalar state).
2. Prove each Quint action is matched by the corresponding extracted
   operation under that relation, sorry-free.
3. Resolve the finite-arithmetic gap (F2) so the relation holds without an
   unproven bound, or carry the bound as a stated, justified assumption.
4. Only then build the `REFINEMENT_VERIFIED` emission path, scoped to the
   relation proved.
