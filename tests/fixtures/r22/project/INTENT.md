# Intent: `jobq` — single-worker job queue with bounded retries

Version: 1.0. Status: reference project for the R22 end-to-end fixture. This
document is the behavioral contract; the Quint spec (`specs/jobq.qnt`)
encodes it, the implementation (`src/queue.rs`) must satisfy it, and the
obligation manifest (`.colosseum/obligations.json`) freezes which clauses
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
- **B3** (idle worker holds no attempts): when no job is running the
  attempt counter is exactly 0. Attempts belong to the in-flight job only.
- **B4** (capacity): `submit` on a queue holding `capacity` pending jobs is
  rejected with `QueueError::Full`; the pending count never exceeds
  `capacity`.
- **W1** (liveness witness): a submitted job can reach the done state. The
  spec must exhibit a trace ending with `done > 0`.

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
  attacker-controlled inputs.
