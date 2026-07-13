VERDICT: BREAKS — the spec's four state invariants (`inv_all`) hold under `quint verify`, but the spec is materially weaker than the intent on several grounded axes: it cannot witness the intent's central "counts only ever increase" and "reaches the failed state" behaviors, its B4 bound contradicts the implementation's parameterized bound, and its two operator constants are numerically equal so verification cannot distinguish them (both demonstrated with passing mutants).

(Voice: claude-agent, fresh colosseum-spec-adversary subagent, Fable 5. Report delivered to the orchestrator after the initial two-voice adjudication was committed; adjudicated in the ADDENDUM.)

### 1. `done`/`failed` monotonicity ("counts only ever increase") has no invariant and is not implied by conservation [serious]
Category: temporal-state mismatch. Affected: spec lines 91-104; INTENT line 43.
INTENT line 43 asserts a transition property: "Done and failed are terminal per job: counts only ever increase." No spec invariant expresses it. `inv_b2` conservation catches only non-conserving single-step changes; a transition that decrements a terminal counter while conserving the identity passes every invariant. Proved empirically: adding a `clawback` action with `failed' = failed - 1, submitted' = submitted - 1` (all other vars held) to the real spec, `quint verify --invariant=inv_all` returns `[ok] No violation found`. A refinement that violates the intent's terminality guarantee is undetectable.
Fix: add a transition-level invariant `done' >= done and failed' >= failed` and make it a required target.

### 2. `CAPACITY == MAX_ATTEMPTS == 3` collapses two independent constants; constant-confusion is unverifiable [serious]
Category: triviality (constant-masking) / refinement mismatch. Affected: spec lines 6-7, 27, 101.
The two operator constants are numerically equal, so any clause referencing the wrong one still verifies. Swapping `queued < CAPACITY` for `queued < MAX_ATTEMPTS` in the submit guard and `inv_b4 = queued <= CAPACITY` for `queued <= MAX_ATTEMPTS`, `quint verify --invariant=inv_all` returns `[ok] No violation found`. In the impl these constants are decoupled (MAX_ATTEMPTS global at queue.rs:9, capacity per-instance at queue.rs:33), so the spec's coincidence hides guard/invariant mix-ups that would be live bugs in code.
Fix: distinct values (e.g. CAPACITY=2, MAX_ATTEMPTS=3); ideally parameterize both.

### 3. Spec's B4 bound (`queued <= 3`) contradicts the impl's parameterized bound (`queued <= capacity`) [serious]
Category: refinement mismatch / contradiction. Affected: spec line 101; queue.rs:230-231, 252.
Spec fixes CAPACITY=3 and proves `queued <= 3`. The kani harness proves a different theorem: capacity in [1,4] with `assert!(q.queued() <= capacity)`. At capacity=4 the impl permits queued=4, violating the spec's inv_b4. The two verification artifacts prove non-equivalent theorems, and the spec cannot replay the b1 test (`new(4)`) or the w1 test (`new(1)`).
Fix: make CAPACITY an instance parameter or verify over a range.

### 4. No reachability witness for the failed/permanent-failure path — B1's core outcome is unverified [serious]
Category: coverage gap. Affected: spec lines 106-109; INTENT lines 19-21.
The spec provides exactly one positive witness, `witness_w1 = done > 0`. B1's defining behavior, "a job whose third attempt fails moves to the failed state," has no `failed > 0` witness. All four safety invariants are vacuously satisfied by an unreachable fail path: an edit making `fail_final`'s guard unsatisfiable keeps `inv_all` green while permanent failure becomes unreachable.
Fix: add `witness_b1_failed = failed > 0` and require a trace reaching it; ideally witness the full retry chain.

### 5. Error-outcome semantics unmodeled; B4 names `QueueError::Full` but the spec only disables the action [serious]
Category: coverage gap / under-specification. Affected: spec lines 25-34; INTENT lines 27-29.
B4 requires rejection "with `QueueError::Full`". The spec encodes a disabled action with no error datum. The impl returns three distinct errors; none is observable in the spec's scalar state, so a conformance bridge cannot check the impl returns the correct error. A bug returning `NotRunning` where `Full` is required passes any state-only replay.
Fix: an `outcome`/`last_error` variable, or explicitly scope error-code conformance out of INTENT.

### 6. `inv_b3` is vacuous in the running case [serious]
Category: coverage gap. Affected: spec line 98; INTENT lines 25-26.
`inv_b3 = not(running) implies (attempts == 0)` constrains only the idle case. Nothing asserts `running implies attempts >= 1`; a refinement reaching `running=true, attempts=0` satisfies inv_b3 vacuously while contradicting the intent.
Fix: strengthen to the biconditional with the attempts bound.

### 7. Missing authoritative artifact: `.colosseum/obligations.json` and the ITF replay adapter are referenced but absent [serious]
Category: contradiction (intent/fixture vs reality). Affected: INTENT line 6; spec line 2; lib.rs:3-6.
INTENT declares the obligation manifest freezes required evidence targets; it does not exist in this working tree (`ls .colosseum` fails). The spec comment and lib.rs reference an ITF replay adapter that ships nowhere in src/.
Fix: add the manifest (including the missing witnesses findings 1 and 4 show) or remove the claim.

### 8. `u32` counters wrap/panic where the spec's `int` is total [cosmetic]
Category: refinement mismatch / edge case. Affected: queue.rs:33-39, 56-63; spec lines 9-14.
After 2^32 increments a counter panics (debug) or wraps (release); `conserved()` can transiently break, a state the spec proves impossible. Unreachable in realistic runs, but a genuine total-vs-partial divergence.
Fix: document an operational bound in INTENT (K3) or use checked/saturating arithmetic.

## META
Attacked: temporal-state mismatch (1, 6), triviality/constant-masking (2), refinement mismatch (2,3,8), coverage gap (4,5,6), contradiction (3,7). No evidence to attack: over-specification (the five actions match the intent's transition graph exactly). Findings 1 and 2 are demonstrated with passing `quint verify` mutants. Confidence: high.
