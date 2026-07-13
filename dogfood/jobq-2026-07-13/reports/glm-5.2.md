I have all three artifacts. Let me cross-reference them systematically before writing the attack report.
VERDICT: BREAKS (the spec is internally consistent for CAPACITY=3 but its invariants are materially weaker than the intent's behavioral clauses, it over-specifies capacity to a single value the intent treats as operator-chosen, and it leaves a temporal-state mismatch in B1 that allows an off-by-one attempt counter to pass all four invariants)

---

### 1. inv_b1 encodes a temporal property as a state bound, losing the "no fourth attempt" guarantee [severity: serious]
- **Category**: temporal-state mismatch
- **Affected**: `specs/jobq.qnt:92` (`inv_b1`), INTENT B1 lines 19-21
- **What's wrong**: INTENT B1 has two parts: (a) "the attempt counter never exceeds MAX_ATTEMPTS (3)" and (b) "A job whose third attempt fails moves to the failed state; there is no fourth attempt." Part (b) is a temporal property about the *number of attempts before exhaustion*. The spec reduces the entire clause to the state invariant `attempts <= MAX_ATTEMPTS`, which is necessary but not sufficient. Concrete scenario: if `start` set `attempts = 0` instead of 1, the machine would execute `start(attempts=0) → fail_retry(0<3, attempts=1) → fail_retry(1<3, attempts=2) → fail_retry(2<3, attempts=3) → fail_final(3==3, exhausted)`, producing **four** fail calls (four attempts) before exhaustion. The invariant `attempts <= 3` holds at every state in this trace because attempts goes 0→1→2→3, never exceeding 3. The spec's invariants cannot distinguish the correct 3-attempt regime from the buggy 4-attempt regime. The spec's `start` action does set `attempts' = 1` (line 42), so the spec itself is correct, but the invariant provides no evidence that this is the case — a modification to `start` that sets `attempts' = 0` would pass `quint verify --invariant=inv_all` while violating B1's "no fourth attempt."
- **Cite (spec)**: > `val inv_b1 = attempts <= MAX_ATTEMPTS` (line 92)
- **Cite (intent)**: > "A job whose third attempt fails moves to the failed state; there is no fourth attempt." (lines 20-21)
- **Fix recommendation**: Add a companion invariant `inv_b1_lower = running implies attempts >= 1` (or equivalently strengthen inv_b3 to be biconditional). This forces `start` to set attempts to at least 1, making the upper-bound invariant meaningful. Without a lower bound, `attempts <= 3` is satisfied by the 4-attempt regime.

### 2. inv_b3 encodes only one direction of B3 — missing the lower bound when running [severity: serious]
- **Category**: under-specification
- **Affected**: `specs/jobq.qnt:98` (`inv_b3`), INTENT B3 lines 25-26, state graph line 37
- **What's wrong**: INTENT B3 says "when no job is running the attempt counter is exactly 0. Attempts belong to the in-flight job only." The spec encodes only the first sentence: `not(running) implies (attempts == 0)`. The state `running = true, attempts = 0` satisfies inv_b3 (antecedent is false, so vacuously true), inv_b1 (0 <= 3), inv_b2 (in-flight counts as 1 regardless of attempts), and inv_b4. All four invariants pass. But the intent's state graph says `start: ... attempts=1` (line 37), so a running job must have at least one attempt. The spec's invariants do not enforce `running implies attempts >= 1`. This is the same root cause as Finding 1 but attacks a different invariant and a different intent clause: inv_b3 is supposed to encode B3, and B3's second sentence ("Attempts belong to the in-flight job only") implies that when a job is in flight, its attempts are positive.
- **Cite (spec)**: > `val inv_b3 = not(running) implies (attempts == 0)` (line 98)
- **Cite (intent)**: > "when no job is running the attempt counter is exactly 0. Attempts belong to the in-flight job only." (lines 25-26); > `start: pending-1, worker busy, attempts=1` (line 37)
- **Fix recommendation**: Strengthen inv_b3 to `inv_b3 = (not(running) implies attempts == 0) and (running implies attempts >= 1)`, or equivalently `(running == (attempts > 0))` if attempts is guaranteed non-negative. This closes the `running=true, attempts=0` gap that undermines both B1 and B3.

### 3. CAPACITY hardcoded to 3 — over-specification that contradicts intent K2 and the implementation [severity: serious]
- **Category**: over-specification / refinement mismatch
- **Affected**: `specs/jobq.qnt:7` (`pure val CAPACITY = 3`), `specs/jobq.qnt:101` (`inv_b4`), INTENT K2 line 55-56, `src/queue.rs:43`
- **What's wrong**: The spec fixes `CAPACITY = 3` as a `pure val`. INTENT K2 says "capacity and MAX_ATTEMPTS are operator-chosen constants, not attacker-controlled inputs" — operator-chosen means the value is not fixed by the contract. The implementation takes `capacity` as a parameter: `pub fn new(capacity: u32) -> Self`. The spec's comment on line 5 claims "Mirrors src/queue.rs," but the implementation has no CAPACITY constant to mirror. The spec's `inv_b4 = queued <= CAPACITY` only verifies B4 for capacity=3. An implementation with capacity=5 (correct per intent) is outside the spec's scope. The Kani proof (`src/queue.rs:230-231`) tests capacity 1-4, which is a different domain than the spec's fixed 3. Neither the spec nor the Kani proof covers capacity > 4. The spec provides evidence only for a single instance of a parameterized machine.
- **Cite (spec)**: > `pure val CAPACITY = 3` (line 7); > `val inv_b4 = queued <= CAPACITY` (line 101); > `// Mirrors src/queue.rs.` (line 5)
- **Cite (intent)**: > "K2: `capacity` and `MAX_ATTEMPTS` are operator-chosen constants, not attacker-controlled inputs." (lines 55-56); > "`submit` on a queue holding `capacity` pending jobs is rejected" (lines 27-28)
- **Fix recommendation**: Parameterize the spec: either make CAPACITY a module parameter (`module jobq(CAPACITY)`) or add a `var capacity: int` to the state with `init` setting it nondeterministically within a bounded range, and change inv_b4 to `queued <= capacity`. This aligns the spec with the intent's operator-chosen semantics and the implementation's parameterized constructor.

### 4. No non-negativity invariants — B2 conservation satisfiable with negative counts [severity: serious]
- **Category**: under-specification
- **Affected**: `specs/jobq.qnt:9-14` (all variables typed `int`), `specs/jobq.qnt:95` (`inv_b2`), INTENT B2 lines 22-24
- **What's wrong**: All six state variables are declared `int` (signed, unbounded). The intent implicitly assumes non-negative counts — you cannot have -3 queued jobs. The spec has no invariant requiring `queued >= 0, done >= 0, failed >= 0, submitted >= 0, attempts >= 0`. Concrete scenario: the state `queued = -1, running = true, attempts = 1, done = 0, failed = 0, submitted = 0` satisfies inv_b2 (`-1 + 1 + 0 + 0 == 0`), inv_b1 (`1 <= 3`), inv_b3 (running is true, antecedent false), and inv_b4 (`-1 <= 3`). All four invariants pass, but the state is nonsensical: a job is running with `submitted = 0` (no job was ever submitted). More practically, an implementation bug that underflows a u32 counter (wrapping to a large positive in release, or a hypothetical signed implementation going negative) could produce states where B2 holds by accident — negative queued compensating for an inflated done — masking the bug. The spec's invariants cannot detect this because they don't enforce non-negativity.
- **Cite (spec)**: > `var queued: int` / `var attempts: int` / `var done: int` / `var failed: int` / `var submitted: int` (lines 9-14); > `val inv_b2 = queued + (if (running) 1 else 0) + done + failed == submitted` (line 95)
- **Cite (intent)**: > "at every observable point, `queued + running + done + failed == submitted`, counting the in-flight job as 1 when the worker is busy. No job is ever lost or duplicated." (lines 22-24)
- **Fix recommendation**: Add `val inv_nonneg = queued >= 0 and attempts >= 0 and done >= 0 and failed >= 0 and submitted >= 0` and include it in `inv_all`. This prevents B2 from being satisfied by sign-cancelling counter pairs and aligns the spec with the intent's implicit non-negativity assumption.

### 5. No monotonicity invariant for done/failed — intent's "counts only ever increase" is unencoded [severity: serious]
- **Category**: coverage gap
- **Affected**: `specs/jobq.qnt:91-104` (invariants section), INTENT line 43
- **What's wrong**: INTENT line 43 states "Done and failed are terminal per job: counts only ever increase." This is a temporal property: across every transition, `done' >= done` and `failed' >= failed`. The spec has no invariant or temporal property encoding this. The four invariants (inv_b1 through inv_b4) are all state-only predicates. Concrete scenario: if an implementation bug decremented both `done` and `submitted` by 1 on some operation, B2 would still hold (`queued + in_flight + (done-1) + failed == (submitted-1)` simplifies to the original equation), inv_b1/b3/b4 would be unaffected, and all invariants would pass. But `done` decreased, violating "counts only ever increase." The spec provides no evidence for this intent clause. The property holds by construction in the spec's actions (no action decrements done or failed), but the invariants don't verify it — a modified action that decrements done would not be caught.
- **Cite (spec)**: > `val inv_all = inv_b1 and inv_b2 and inv_b3 and inv_b4` (line 104) — no monotonicity invariant present
- **Cite (intent)**: > "Done and failed are terminal per job: counts only ever increase." (line 43)
- **Fix recommendation**: Add a temporal property or a transition-level invariant: either `val inv_monotonic = done' >= done and failed' >= failed` evaluated after each step, or encode it as a state invariant by tracking previous values. In Quint, this can be expressed as a temporal formula or by adding `old_done`/`old_failed` ghost variables updated in each action with an invariant `done >= old_done and failed >= old_failed`.

### 6. No monotonicity invariant for submitted — "no job ever lost" can be circumvented with compensating decrements [severity: serious]
- **Category**: coverage gap
- **Affected**: `specs/jobq.qnt:95` (`inv_b2`), INTENT line 24
- **What's wrong**: INTENT line 24 says "No job is ever lost or duplicated." B2 encodes this as a conservation identity, but conservation alone does not prevent loss if two counters move in compensating directions. Concrete scenario: an implementation bug that decrements both `submitted` and `done` by 1 on some spurious operation preserves B2 (`queued + in_flight + (done-1) + failed == (submitted-1)` is equivalent to the original), but a completed job has been "un-completed" and "un-submitted" — a job was lost from the terminal count. The spec has no invariant requiring `submitted' >= submitted` (monotonicity of submitted). Combined with Finding 5 (no monotonicity for done/failed), the spec's invariants cannot detect a class of bugs where counters are jointly decremented. The intent's "no job is ever lost" is a stronger claim than B2 alone.
- **Cite (spec)**: > `val inv_b2 = queued + (if (running) 1 else 0) + done + failed == submitted` (line 95)
- **Cite (intent)**: > "No job is ever lost or duplicated." (line 24)
- **Fix recommendation**: Add `submitted' >= submitted` as a transition invariant (or track `old_submitted` with `submitted >= old_submitted`). Combined with the monotonicity fix from Finding 5, this ensures all monotonic counters only increase, preventing compensating-decrement bugs from hiding behind B2.

### 7. int vs u32 composition failure — spec's unbounded model masks implementation overflow [severity: serious]
- **Category**: composition failure
- **Affected**: `specs/jobq.qnt:9-14` (`int` types), `src/queue.rs:34-39` (`u32` types), `src/queue.rs:56-63` (`submit`), `src/queue.rs:129-132` (`conserved`)
- **What's wrong**: The spec models all counters as `int` (unbounded mathematical integers). The implementation uses `u32` (unsigned 32-bit). The implementation's `submit` does `self.submitted += 1` (line 61) and `self.queued += 1` (line 60) without overflow checks. After 2^32 successful submit/start/complete cycles, `submitted` wraps to 0 while `done` may be large, breaking B2 conservation in the implementation. The spec's `int` model never overflows, so it cannot detect this. The Kani proof (`src/queue.rs:233`) runs only 10 iterations, far below the 2^32 threshold. The spec provides no acknowledgment of this refinement gap — no overflow precondition, no bound on `submitted`, no note that the `int` model is an idealization of `u32`. For the Colosseum methodology, the spec is supposed to be evidence for the implementation; this composition failure means the spec's B2 holds mathematically but can fail in the implementation under sustained load.
- **Cite (spec)**: > `var queued: int` / `var submitted: int` (lines 9, 14)
- **Cite (intent)**: > "No job is ever lost or duplicated." (line 24) — overflow-induced conservation violation is a form of job loss
- **Fix recommendation**: Either (a) add a precondition to B2 stating `submitted < 2^32` (honest refinement), or (b) add an invariant `submitted < 4294967296` to the spec and note that the implementation uses u32, or (c) use `nat` in the spec and document that the implementation's u32 is a bounded refinement requiring `submitted < 2^32` for B2 to hold.

### 8. Error returns not modeled — intent's "rejected with QueueError::Full" has no spec-level encoding [severity: cosmetic]
- **Category**: coverage gap
- **Affected**: `specs/jobq.qnt:26-34` (`submit` action), INTENT B4 line 28, `src/queue.rs:12-19` (`QueueError`)
- **What's wrong**: INTENT B4 says "submit on a queue holding capacity pending jobs is rejected with `QueueError::Full`." The spec models this as a guard (`queued < CAPACITY`) that prevents the transition from firing. The guard is equivalent to rejection in terms of state evolution, but the spec does not model the error return itself. An implementation that silently ignores submit when full (no error, no state change) would satisfy the spec's transition system but violate the intent's "rejected with QueueError::Full." The implementation defines three error types (`Full`, `NotStartable`, `NotRunning`); the spec models none of them. This is standard for state-machine specs (guards replace errors), but the intent explicitly names the error type as part of B4, and the spec's encoding is a refinement that drops the error channel.
- **Cite (spec)**: > `action submit = all { queued < CAPACITY, queued' = queued + 1, ... }` (lines 26-34) — no error model
- **Cite (intent)**: > "`submit` on a queue holding `capacity` pending jobs is rejected with `QueueError::Full`" (lines 27-28)
- **Fix recommendation**: Either accept this as a known refinement (state-machine specs model guards, not error channels) and document it in a comment, or add an explicit `submit_rejected` action that fires when `queued == CAPACITY` and stutters (no state change), making the rejection path visible in the transition system.

---

## META

**Categories attacked**:
- temporal-state mismatch (Finding 1) — the strongest finding; B1's "no fourth attempt" is temporal, encoded as a state bound
- under-specification (Findings 2, 4) — inv_b3 missing lower bound; no non-negativity invariants
- over-specification / refinement mismatch (Finding 3) — CAPACITY hardcoded
- coverage gap (Findings 5, 6, 8) — monotonicity of done/failed, monotonicity of submitted, error returns
- composition failure (Finding 7) — int vs u32 overflow gap

**Categories I did not have evidence to attack**:
- triviality: all four invariants impose real constraints; none are vacuously satisfied by the init state or by the action structure alone
- ambiguity: the spec's Quint syntax is unambiguous; `if (running) 1 else 0` is a standard conditional
- contradiction (internal): all five actions preserve all four invariants (verified by hand-tracing each action against each invariant); the spec is internally consistent
- impossibility-hypothesis vacuity: no hypotheses in the spec (pure state machine)
- disjunction-vs-decomposition collapse: no hardness assumptions
- preconditional over-strength: no axioms or theorems with preconditions
- edge case (empty/maximum): capacity=0 is outside the spec's scope (consequence of Finding 3, not a separate edge-case finding); the spec has no maximum-value edge cases because `int` is unbounded

**Artifacts I would have wanted access to**:
- `.colosseum/obligations.json` — referenced by INTENT.md line 6-7 but not present in the repo; would reveal which clauses are required evidence targets and whether the missing monotonicity/non-negativity invariants are obligated
- Quint verification output (`quint verify --invariant=inv_all` and `quint run --invariant=witness_w1_negated` traces) — would confirm whether the spec actually passes verification and whether the W1 witness trace is found
- Prior spec versions — would reveal whether the invariant weakening was intentional or a regression

**Estimated confidence in verdict**: high. The temporal-state mismatch (Finding 1) and the CAPACITY over-specification (Finding 3) are grounded in exact text from all three artifacts and are independently verifiable by tracing the spec's actions. The non-negativity and monotonicity gaps (Findings 4-6) follow directly from the spec's invariant definitions and the intent's explicit behavioral clauses. The int/u32 composition failure (Finding 7) is a standard but real refinement gap.
