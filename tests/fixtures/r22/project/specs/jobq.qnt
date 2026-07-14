// jobq.qnt — Quint encoding of the INTENT.md job-queue machine (B1-B5, W1-W2).
// Scalar state only, so the itf-replay v1 line protocol can carry every
// variable (ints and booleans). prev_done/prev_failed are ghost variables:
// they carry the previous state's terminal counts so monotonicity (B5) is
// expressible as a state invariant (a plain invariant cannot see across a
// transition; the C7 adjudication's clawback mutant proved the gap).
//
// CAPACITY is a module constant (INTENT K2: operator-chosen, decoupled from
// MAX_ATTEMPTS). The concrete `jobq` module below pins CAPACITY = 2 and is
// the file's default main (replay traces and witness runs use it); jobq_c4
// pins the kani harness's domain edge. Verification runs BOTH, so inv_b4 is
// established for more than one instance, and the default capacity (2) is
// deliberately distinct from MAX_ATTEMPTS (3): a guard or invariant that
// references the wrong constant no longer verifies by numeric coincidence
// (the C7 adjudication's constant-swap mutant proved that gap too).
module jobqP {
  const CAPACITY: int

  // Attempt budget per job. Mirrors src/queue.rs MAX_ATTEMPTS.
  pure val MAX_ATTEMPTS = 3

  var queued: int
  var running: bool
  var attempts: int
  var done: int
  var failed: int
  var submitted: int
  // Ghost: previous state's terminal counts (B5).
  var prev_done: int
  var prev_failed: int

  action init = all {
    queued' = 0,
    running' = false,
    attempts' = 0,
    done' = 0,
    failed' = 0,
    submitted' = 0,
    prev_done' = 0,
    prev_failed' = 0,
  }

  // submit: admit one job to the pending queue (B4 guard).
  action submit = all {
    queued < CAPACITY,
    queued' = queued + 1,
    submitted' = submitted + 1,
    running' = running,
    attempts' = attempts,
    done' = done,
    failed' = failed,
    prev_done' = done,
    prev_failed' = failed,
  }

  // start: one pending job goes in flight; first attempt begins (B3).
  action start = all {
    queued > 0,
    not(running),
    queued' = queued - 1,
    running' = true,
    attempts' = 1,
    done' = done,
    failed' = failed,
    submitted' = submitted,
    prev_done' = done,
    prev_failed' = failed,
  }

  // complete: the in-flight job finishes.
  action complete = all {
    running,
    running' = false,
    attempts' = 0,
    done' = done + 1,
    queued' = queued,
    failed' = failed,
    submitted' = submitted,
    prev_done' = done,
    prev_failed' = failed,
  }

  // fail_retry: attempt failed within budget; job stays in flight (B1).
  action fail_retry = all {
    running,
    attempts < MAX_ATTEMPTS,
    attempts' = attempts + 1,
    running' = running,
    queued' = queued,
    done' = done,
    failed' = failed,
    submitted' = submitted,
    prev_done' = done,
    prev_failed' = failed,
  }

  // fail_final: budget exhausted; job permanently failed (B1 terminal).
  action fail_final = all {
    running,
    attempts == MAX_ATTEMPTS,
    running' = false,
    attempts' = 0,
    failed' = failed + 1,
    queued' = queued,
    done' = done,
    submitted' = submitted,
    prev_done' = done,
    prev_failed' = failed,
  }

  action step = any {
    submit,
    start,
    complete,
    fail_retry,
    fail_final,
  }

  // B1: the attempt counter never exceeds the budget.
  val inv_b1 = attempts <= MAX_ATTEMPTS

  // B2: conservation — no job lost or duplicated.
  val inv_b2 = queued + (if (running) 1 else 0) + done + failed == submitted

  // B3 (biconditional): attempts belong to the in-flight job only, and an
  // in-flight job always has an attempt underway (C7 finding F1).
  val inv_b3 = (not(running) implies (attempts == 0))
    and (running implies (attempts >= 1 and attempts <= MAX_ATTEMPTS))

  // B4: pending count respects capacity.
  val inv_b4 = queued <= CAPACITY

  // B5: terminal counts are monotone (ghost encoding; C7 finding F4).
  val inv_mono = done >= prev_done and failed >= prev_failed

  // Non-negativity: implied by construction, asserted so the invariant set
  // stands alone as evidence (C7 finding F1).
  val inv_nonneg = queued >= 0 and attempts >= 0 and done >= 0
    and failed >= 0 and submitted >= 0

  // All required invariants, for one-shot `quint verify --invariant=inv_all`.
  val inv_all = inv_b1 and inv_b2 and inv_b3 and inv_b4 and inv_mono and inv_nonneg

  // W1: liveness witness — `quint run --invariant=witness_w1_negated`
  // searching for a violation exhibits a trace reaching done > 0.
  val witness_w1 = done > 0
  val witness_w1_negated = not(witness_w1)

  // W2: failure-path witness — the permanent-failure outcome is reachable
  // (C7 finding F7: without this, an unsatisfiable fail_final guard would
  // keep every safety invariant green while gutting B1).
  val witness_b1_failed = failed > 0
  val witness_b1_failed_negated = not(witness_b1_failed)
}

// Default instance: the file's main module. CAPACITY = 2, deliberately
// distinct from MAX_ATTEMPTS = 3.
module jobq {
  import jobqP(CAPACITY = 2).*
}

// The kani harness's domain edge (capacity in 1..4).
module jobq_c4 {
  import jobqP(CAPACITY = 4).*
}
