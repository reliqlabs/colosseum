# Intent: `jobq` — single-worker job queue with bounded retries

Version: 1.1 (strengthened per the 2026-07-13 panel adjudication,
`dogfood/jobq-2026-07-13/ADJUDICATION.md`: B3 made biconditional, B5 and W2
added, K3 added; clause IDs stable, nothing renumbered). Status: reference
project for the R22 end-to-end fixture. This
document is the behavioral contract; the Quint spec (`specs/jobq.qnt`)
encodes it, the implementation (`src/queue.rs`) must satisfy it, and the
obligation manifest (`.fv/obligations.json`) freezes which clauses
are required evidence targets.

## Purpose

`jobq` admits submitted jobs into a queue and processes them one at a time.
A processing attempt either completes the job or fails; a failed attempt is
retried until the attempt budget is exhausted, after which the job is
permanently failed. The queue never loses a job and never exceeds its
configured capacity.

## Behavioral clauses

- **B1** (bounded retries): the attempt counter never exceeds
  `MAX_ATTEMPTS` (3). A job whose third attempt fails moves to the failed
  state; there is no fourth attempt.
- **B2** (conservation): at every observable point,
  `queued + running + done + failed == submitted`, counting the in-flight
  job as 1 when the worker is busy. No job is ever lost or duplicated.
- **B3** (attempts track the in-flight job, both directions): when no job
  is running the attempt counter is exactly 0, and when a job is in flight
  the counter is between 1 and `MAX_ATTEMPTS`. Attempts belong to the
  in-flight job only.
- **B4** (capacity): `submit` on a queue holding `capacity` pending jobs is
  rejected with `QueueError::Full`; the pending count never exceeds
  `capacity`.
- **B5** (terminal monotonicity): the done and failed counts never
  decrease. Done and failed are terminal per job; no operation claws a
  finished job back.
- **W1** (liveness witness): a submitted job can reach the done state. The
  spec must exhibit a trace ending with `done > 0`.
- **W2** (failure-path witness): a submitted job can reach the permanently
  failed state through attempt exhaustion. The spec must exhibit a trace
  ending with `failed > 0`.

## State transition graph

```
submit:   pending+1                       (guard: pending < capacity)
start:    pending-1, worker busy, attempts=1   (guard: pending>0, idle)
complete: worker idle, done+1, attempts=0      (guard: busy)
fail:     attempts<MAX  -> attempts+1, stays busy
          attempts==MAX -> worker idle, failed+1, attempts=0
```

Done and failed are terminal per job: counts only ever increase.

## Non-goals

- Multiple concurrent workers (single worker by design).
- Job identity, payloads, priorities, or reordering (counts only).
- Persistence across restarts.

## Trust assumptions

- K1: callers drive the queue from a single thread (no interior
  synchronization is provided or claimed).
- K2: `capacity` and `MAX_ATTEMPTS` are operator-chosen constants, not
  attacker-controlled inputs. The spec verifies the machine at capacities 2
  and 4 (distinct from `MAX_ATTEMPTS` so constant-reference mix-ups cannot
  verify by numeric coincidence); the kani harness covers capacities 1-4.
- K3: error VALUES are code-level contract, not spec state. The spec models
  rejection as the absence of an enabled transition; which `QueueError`
  variant a rejected call returns is enforced by the unit tests and cited
  in the trust ledger, and is out of scope for spec-to-code conformance
  replay (C7 adjudication, finding F5).
