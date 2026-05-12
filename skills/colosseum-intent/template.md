# Intent: <System Name>

> Colosseum intent document. The human-anchored source of truth for what this system should do. Every downstream spec, proof, and test is bounded by the quality of this document. Last revised: <date>.

## 1. System Identity

- **Name:** <one-line name>
- **Scope:** <function / module / service — be specific>
- **Purpose:** <one sentence describing what this system does and why it exists>

## 2. Behaviors

Concrete input/output pairs across typical, boundary, and edge cases. Each behavior is a worked example. If a spec writer reads only this section, they should be able to characterize the system's input-output relation.

### 2.1 Happy path

**Input:** <concrete example>
**Output:** <concrete example>
**Notes:** <why this is the canonical use case>

### 2.2 Boundary cases

- **Input:** <e.g. empty input, single element, maximum size> → **Output:** <expected>
- **Input:** <another boundary> → **Output:** <expected>

### 2.3 Edge cases

- **Input:** <unusual but valid input> → **Output:** <expected>
- **Input:** <input near system limits> → **Output:** <expected>

### 2.4 Explicit failures

Inputs that the system rejects or handles non-normally. See Section 4 for full handling detail.

- **Input:** <example> → **Outcome:** <rejection mode>

### 2.5 Structured behavior blocks (state-machine systems only)

For systems whose behavior is naturally state-machine-shaped — sessions, protocols, multi-step workflows, transactional flows — use the block form below. Each block names a transition with explicit pre- and post-conditions. The structure makes **contradictions visible**: two blocks that demand contradictory preconditions on the same from-state stand out on inspection rather than hiding in prose.

This section also maps mechanically to downstream specs: each block becomes a Quint `action` (with `Requires` as the action's guard), and the from-state / to-state pair becomes a Lean refinement target.

For pure-functional systems with no observable state, skip this section. Mark `N/A — pure computation` and explain.

#### Block: <transition name>

- **From state:** <named state or predicate over state variables>
- **Trigger:** <action / input / event>
- **Requires (positive precondition):** <conjunction of predicates that MUST hold over the from-state>
- **Forbids (negative precondition):** <predicates that, if true, disqualify this transition>
- **Produces (postcondition):** <conjunction of predicates over the to-state>
- **To state:** <named state or predicate over state variables>
- **On precondition failure:** <named failure mode from Section 4>

#### Block: <next transition>

- **From state:**
- **Trigger:**
- **Requires:**
- **Forbids:**
- **Produces:**
- **To state:**
- **On precondition failure:**

#### Cross-block discipline

Before moving on, eyeball the block list:

- For any state that appears as **From state** in two or more blocks: are the **Requires** clauses mutually consistent, or do they describe different mutually-exclusive cases? Mutually exclusive is fine; overlapping-and-contradictory is a bug.
- For any state that appears as **To state**: does at least one block reaching it have an obvious entry path?
- For any state name introduced: is it defined? Implicit states are the most common source of downstream spec ambiguity.

## 3. Invariants

Properties that are always true. If any of these is violated, the system is broken regardless of input.

### 3.1 Structural invariants

Properties of the data the system manipulates. Each invariant should be a single clause that can be evaluated against the data alone — no quantification over operations or time.

- <invariant 1>: <statement>
- <invariant 2>: <statement>

### 3.2 Behavioral invariants

Relationships between operations or over time. State explicitly whether each is a **state invariant** (true at every point in any reachable state) or a **temporal property** (a claim about the *sequence* of states, e.g., "if X is ever observed, Y must have been observed earlier"). The distinction is load-bearing: state invariants can be discharged by Apalache / Kani at every state; temporal properties require explicit temporal-formula formulation. Conflating the two produces the `temporal_state_mismatch` attack category — a spec that looks green but doesn't capture what was intended.

- <invariant 1> [**state** | **temporal**]: <statement>
- <invariant 2> [**state** | **temporal**]: <statement>

## 4. Failure Modes

Named scenarios where the system does not produce a normal output. For each: cause, expected handling, and whether the failure is recoverable.

### 4.1 <Failure name>

- **Cause:** <what triggers this>
- **Handling:** <panic / typed error / default value / log + skip — be specific>
- **Recoverable:** <yes/no — and what recovery means>

### 4.2 <Failure name>

- **Cause:**
- **Handling:**
- **Recoverable:**

## 5. Non-Goals

Things this system explicitly does NOT do. Prevents over-specification and clarifies scope.

- <non-goal 1>
- <non-goal 2>
- <non-goal 3>

## 6. Trust Boundaries

What the system assumes about its environment. Where input validation begins and ends.

- **Caller contract:** <what callers must guarantee>
- **External systems:** <what's assumed about OS / network / dependencies>
- **Input domain:** <expected input shape; what's validated and what's trusted>
- **Output contract:** <what callers can rely on from outputs>

## 7. Performance Bounds

Only if performance is correctness-relevant. Otherwise, mark `N/A` and explain why.

- <bound 1>: <e.g. terminates in at most N rounds for N candidates>
- <bound 2>: <e.g. memory usage bounded by O(n) in input size>

## 8. Concrete Scenarios

Narrative walkthroughs of key flows. Each scenario is a short story. Specs and tests derive directly from these.

### 8.1 <Scenario name>

> Given <initial state>, when <action>, the system <step 1>, then <step 2>, ending in <final state>.

Detailed step-by-step:
1. <step>
2. <step>
3. <step>

### 8.2 <Scenario name>

> ...

### 8.3 <Scenario name>

> ...

---

## Open Questions

`TBD:` markers — questions the user could not answer at intent-doc time but that downstream specs will need resolved. Surface these for follow-up before formal spec writing.

- TBD: <question>
- TBD: <question>

## Revision Log

- <date> — initial draft
- <date> — revised after tracer-bullet prototype (Section 2 expanded with three new edge cases)
