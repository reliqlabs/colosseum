---
version: 0.1.0   # SemVer MAJOR.MINOR.PATCH — see "SemVer convention" under Version History
status: draft    # draft | active | superseded
---

# Intent: <System Name>

> FV intent document. The human-anchored source of truth for what this system should do. Every downstream spec, proof, and test is bounded by the quality of this document. `status` above is `draft` until the first adversarial pass, `active` once it is the current source of truth for downstream specs, `superseded` once a later intent document replaces it. See Version History below for what changed and why.

## Version History

Every revision gets an entry here, newest first. This section is the append-only record of what changed and why — it supersedes any earlier practice of marking a removed clause in place with `~~strikethrough~~` or an inline `REMOVED`/`RESERVED` placeholder left in the document body. **The document above carries current truth only.** When a clause is removed or superseded, retire its ID here explicitly (see below) rather than leaving a marker at its old location; downstream tools resolve an ID via this history, not via a slot number in the live text.

**SemVer convention** (applied to the `version` frontmatter field above; aligned with the SemVer proposal in `methodology-improvements.md` §"Intent doc + boundary doc + spec versioning via SemVer", refined against dogfood revision practice across multiple projects):

- **MAJOR** — a `B*`/`S*`/`T*`/`K*` clause's meaning changes, is weakened, or is removed; a trust assumption (`K*`) is widened; a behavior previously specified becomes unspecified; or a clause is rewritten because the prior statement was discovered to be provably false or vacuous.
- **MINOR** — a new `B*`/`S*`/`T*`/`K*` clause is added; an existing clause's scope is narrowed (a strictly stronger guarantee, e.g. a trust boundary tightened); a new failure mode, scenario, defined symbol/predicate, or encoding-discipline note (`A*`) is added.
- **PATCH** — wording, notation, cross-reference, or status-block changes only — no clause's semantic content changes.

**ID retirement discipline**: once assigned, a clause ID (`S*`/`B*`/`T*`/`K*`/`A*`) is never reused, even after its clause is removed — downstream artifacts (obligation manifests, the compose ledger, adversarial attack reports, Quint/Lean spec citations) key on these IDs across versions, and a reused ID silently corrupts that history. When a version entry below removes a clause, list its ID under **Retired** so the next author doesn't reassign it.

### <version> — <date> — <MAJOR | MINOR | PATCH>

<One paragraph: what changed and why. Cite the adversarial report, finding, or prototype gap that drove it, if any.>

- **Added:** <new clause IDs, one line each>
- **Changed:** <existing clause IDs and what changed about them>
- **Retired:** <clause IDs removed this revision — never reassign these> (omit this line if none)

### v0.1.0 — <date> — initial draft

Initial elicitation pass via `fv-intent`.

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

### 2.6 Field specifications

For every piece of protocol-visible state or message payload introduced above (state variables, message/transaction payloads, published outputs): a per-field table. This is the structure that most reliably catches byte-level bugs (wrong width, wrong nullability, wrong ownership) before they survive into a formal spec — dogfooding this methodology found under-specified field shape to be a recurring root cause once specs went byte-precise (canonical serialization layouts, attestation report-data layouts, and similar).

| Field | Type | Units | Range | Nullable | Written by |
|---|---|---|---|---|---|
| `<name>` | `<e.g. u64, Vec<Addr>, [u8; 32]>` | `<e.g. seconds since epoch, bytes, n/a>` | `<e.g. 1 ≤ x ≤ candidates.len()>` | `<yes/no — and what absence means>` | `<the handler/component that writes it, and whether it's write-once or mutable>` |

For pure-functional systems with no structured field-level state or message schema, mark `N/A — no structured field-level state` and explain (mirrors the 2.5 pure-computation escape hatch).

## 3. Invariants

Properties that are always true. If any of these is violated, the system is broken regardless of input. Every invariant clause below carries a **stable ID**, assigned once and never reused even after the clause is removed (see Version History). Downstream artifacts — obligation manifests, the compose ledger, adversarial attack reports, Quint/Lean spec citations — key on these IDs, not on section numbers or prose position: §-numbering may shift as the document grows; the ID does not.

### 3.1 Structural invariants — `S*`

Properties of the data the system manipulates, evaluable against the data alone — no quantification over operations or time.

- **S1** — <statement>
- **S2** — <statement>

### 3.2 Behavioral invariants — `B*`

Properties evaluable at a single reachable state: relationships between operations, or between state variables, that hold pointwise without needing the trajectory of how that state was reached. **Temporal claims — those requiring a sequence of states — do not belong here; see Section 3.3.** Tag each clause with its discharge shape; the four-tag vocabulary below is what dogfooding this methodology surfaced as necessary, not a suggestion to invent your own taxonomy:

- **state** — a plain relationship between state variables, or between an operation's pre/post state, checkable by Kani- / Apalache-style state predicates.
- **cross-layer** — the witness spans components (on-chain + off-chain, protocol + circuit, chain + enclave); no single-layer tool discharges it alone (see `fv-compose`).
- **off-chain** — the claim is about a component outside the tool's model (an external service, a build/deploy pipeline, an operator process).
- **meta-security** — a probabilistic / negligibility-bound claim (an adversary-advantage bound), not a deterministic predicate.

- **B1** [state]: <statement>
- **B2** [cross-layer]: <statement>

### 3.3 Temporal properties — `T*`

Claims about a *sequence* of states — "if X is ever observed, Y must have been observed earlier," "once true, stays true," "eventually reaches." These require an explicit temporal-formula formulation downstream (Quint temporal operators, TLA+, or a Lean trajectory relation), not a single-state predicate.

**Do not fold a temporal claim into Section 3.2, and do not state a `B*` clause as if it needed history when it doesn't.** The distinction is load-bearing: conflating the two is exactly the `temporal_state_mismatch` failure mode the `fv-spec-adversary` (see `fv-adversarial`) is tuned to find. For every `T*` clause, make sure at least one Concrete Scenario (Section 8) exercises a sequence where the property could plausibly be violated — a temporal property with no scenario-level witness is vacuous in practice.

- **T1** — <statement, e.g. `always (P → always Q)`>
- **T2** — <statement>

> *Compatibility note:* earlier FV dogfood documents (predating this template revision) numbered temporal claims inside the `B*` series with an inline `[temporal]` tag rather than a separate `T*` series (alongside `[state]`, `[cross-layer]`, `[off-chain]`, `[meta-security]` tags on the same series). Both forms are readable, and this template does not require retroactively renumbering an existing document's `B*` series to match — that renumbering is itself a MAJOR-classified change for no semantic gain. New documents authored against this template use the `T*` split, since it lets downstream tooling (e.g. the compose ledger's `claim_id` filtering) select temporal claims without parsing prose tags.

### 3.4 Encoding-discipline notes — `A*`

Constraints on **how** a clause above must be encoded by downstream formal specs — not new invariant content, a constraint on its formal encoding. These typically originate from a `fv-adversarial` Section D finding (a multi-voice fan-out generated materially different encodings of the same clause — divergence that re-running fan-out reproduces, so it isn't stochastic noise) and are consumed directly by the `quint-spec-generator` agent (`agents/fv-quint-spec-generator.md`, which is instructed to honor any encoding-discipline note the intent carries), and by any Lean / Verus / Kani spec author encoding the same clause. Adding one is a MINOR version bump — it constrains an encoding, it does not change invariant content.

| ID | Constrains | Discipline |
|----|-----------|------------|
| A1 | <clause ID, e.g. B2> | <e.g. "MUST be encoded as a checkable state invariant over a snapshot variable; an action-guard-only encoding is insufficient — nothing flags an action-set drift that bypasses the guard."> |
| A2 | <clause ID, e.g. S6> | <e.g. "Downstream Lean specs MUST carry `1 ≤ cs.length` as an explicit hypothesis; the weaker `cs.Nodup` alone does not preclude the empty set."> |

Leave this table empty (`None yet — will accumulate as adversarial fan-out surfaces encoding divergence.`) on first authoring; it is expected to grow over the document's life, not be filled in up front.

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

### 6.1 Boundary contract

- **Caller contract:** <what callers must guarantee>
- **External systems:** <what's assumed about OS / network / dependencies>
- **Input domain:** <expected input shape; what's validated and what's trusted>
- **Output contract:** <what callers can rely on from outputs>

### 6.2 Trust assumptions — `K*`

Out-of-model assumptions this document's guarantees rest on: things no layer of this system's own verification checks, taken as axioms — off-chain honesty, cryptographic hardness, external-component correctness. Each gets a stable ID so a waiver, an axiom annotation in a downstream Lean/Verus spec, or a compose-ledger entry can cite it directly. (These correspond to the compose ledger's `externally-assumed` evidence class — see `fv-compose`.) The letter is `K*`, not `A*`: `A*` is reserved for encoding-discipline notes (Section 3.4), which is a separate ID space in already-dogfooded practice.

- **K1** — <e.g. "the off-chain component X behaves honestly">: <statement, and what would break if false>
- **K2** — <e.g. "SHA-256 is collision-resistant">: <statement>

Removing or weakening a `K*` assumption without discharging it (turning it from an axiom into a theorem some layer proves) is a MAJOR version bump; narrowing one (e.g. an assumption moves to a proven guarantee, shrinking what's left assumed) is MINOR.

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
