// jobq.qnt — Quint encoding of the INTENT.md job-queue machine (B1-B4, W1).
// Scalar state only, so the itf-replay v1 line protocol can carry every
// variable (ints and booleans).
module jobq {
  // Operator constants (INTENT K2). Mirrors src/queue.rs.
  pure val MAX_ATTEMPTS = 3
  pure val CAPACITY = 3

  var queued: int
  var running: bool
  var attempts: int
  var done: int
  var failed: int
  var submitted: int

  action init = all {
    queued' = 0,
    running' = false,
    attempts' = 0,
    done' = 0,
    failed' = 0,
    submitted' = 0,
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

  // B3: attempts belong to the in-flight job only.
  val inv_b3 = not(running) implies (attempts == 0)

  // B4: pending count respects capacity.
  val inv_b4 = queued <= CAPACITY

  // All required invariants, for one-shot `quint verify --invariant=inv_all`.
  val inv_all = inv_b1 and inv_b2 and inv_b3 and inv_b4

  // W1: liveness witness — `quint run --invariant=witness_w1_negated`
  // searching for a violation exhibits a trace reaching done > 0.
  val witness_w1 = done > 0
  val witness_w1_negated = not(witness_w1)
}
