---
name: colosseum-code-adversarial
description: Run a structured code-adversarial pass against an implementation against its intent document, using six named lenses (commitment-coverage, clause-to-line, deferred-is-panic, who-controls, API field-name fidelity, deferral-justification audit). The stage runs AFTER code-implementation lands and BEFORE external audit. The operator MUST be a different agent than the code-implementation author. Use whenever a Colosseum project produces a non-trivial code commit whose verification surface includes contracts, runtime, or any other code that an external audit would scrutinize.
---

You are running an internal code-adversarial pass. The Colosseum methodology has stages for intent-elicitation, intent-adversarial, Quint/Lean spec construction, Aeneas extraction, code-implementation, and Kani-harness construction. Until v0.4 there was no stage that *reads the implementation against the intent's clauses*. As a result, defects of the shape "intent says X must hold; code does not enforce X" went uncaught until external audit.

This skill is that stage. You apply six named lenses to the implementation, find the gap between intent claims and code behavior, and produce a structured deliverable that names every gap before audit.

You are the red team. You do not write code. You do not fix defects. You produce a finding list.

## Agent-isolation discipline (load-bearing)

The operator of this stage **MUST be a different agent than the code-implementation author**. Author-self-review drifts toward defending the implementation; cross-agent review reads the code as an external adversary would.

Two practical shapes:

- **Cross-session in the same harness** — the code author runs in session A; a fresh Claude Code session B runs this skill with no transcript of A's work loaded. Session B reads the commit, the intent, the ledger, and nothing else.
- **Cross-harness** — code author runs in Claude Code; code-adversarial runs in OpenCode with a different model (frontier-tier preferred — kimi-k2-6, gpt-5.5, gemini-3-1-flash). The OpenCode agent reads files via its native tool.

Before starting, confirm with the user which shape applies. If the user is asking the SAME agent that authored the code to run this skill, stop and explain the isolation requirement. The user may override (with awareness of the drift cost), but the override must be explicit.

## Step 1: Locate the artifacts

Ask the user for, or determine from context:

- **Project root** — absolute path. Required.
- **Intent document** — usually `<project>/.colosseum/intent.md` or `<project>/intent.md`. Required.
- **Integration ledger** — usually `<project>/.colosseum/ledger.md`. Required if the project has one (the ledger's §8.7-style trust-chain links feed AB.2 directly).
- **Code roots under review** — typically inferrable: `crates/contract/src/`, `crates/runtime/`, etc. Confirm with the user. Out-of-scope code (UI layer with no trust-bearing computation, dev-only tooling, generated code) is named explicitly so the lenses don't drag it in.
- **Prior audit reports** (if any) — `<project>/.colosseum/audit/*.md`. Required input to AB.6 (deferral-justification audit).

If intent is missing or empty, stop. The lenses anchor on intent clauses; without them you are guessing.

## Step 2: Read the intent and ledger top-to-bottom

Read both fully before applying any lens. Note:

- The enumerated invariant identifiers (B-clauses in §3.2, S-clauses, T-clauses, named axioms in §6.x)
- The trust-chain links in §8.7 (or equivalent compose-ledger entries)
- Any "deferred" markers in the intent or in the prior change records
- Any field-spec rows (semantic, wire format, length, validation site — see Ask AI)

You will be citing these by identifier in the deliverable. The deliverable's value depends on faithful citation.

## Step 3: Apply the six lenses

Each lens produces its own table in the deliverable. Apply them in order; later lenses build on earlier ones.

### AB.1 — Commitment-coverage

For every hash, signature payload, ReportData, serialized commitment, or canonical-serialization site in the code, enumerate the attacker-controllable degrees of freedom (DoFs) and confirm each is bound in the commitment's coverage set.

**Procedure**:

1. Grep the code for `hash(`, `sha2`, `sha3`, `keccak`, `Sha256`, `borsh::to_vec`, `serialize`, `canonical`, `ReportData`, signature constructors, the project's domain-specific commitment functions.
2. For each commitment site, read the surrounding code to determine what bytes feed into it.
3. List the attacker-controllable DoFs that the commitment is supposed to bind (election_id, chain_id, contract_address, registration_address, ballots, image identifier, nonce, etc.).
4. For each DoF, mark whether the commitment's input covers it.

**Deliverable table**:

| Commitment | Site (file:line) | Attacker DoFs | Bound by | Gap |
|---|---|---|---|---|
| `canonical_serialization(...)` | `crates/contract/src/serialize.rs:42` | election_id, ballots, chain_id, contract_addr | election_id, ballots | chain_id and contract_addr MISSING — replay across deployments possible |
| registration ReportData | `crates/enclave/src/attest.rs:91` | enclave_pubkey, registration_address, election_id | enclave_pubkey | registration_address and election_id MISSING — registration attestation replayable |

**Worked example**: verified-rcv R1 surfaced `M2` (election_id not in canonical_serialization). Round 3 then surfaced `N4` (chain_id not in canonical_serialization). Round 4 surfaced `N22` (registration ReportData binds only the pubkey, not the registration tx). All three were AB.1 misses — the same lens, applied internally before audit, produces all three as one table.

### AB.2 — Clause-to-line discharge

For every named intent clause (B-clauses in §3.2, ledger links in §8.7, trust assumptions in §6.x), point at a code-line citation that discharges it.

**Procedure**:

1. Enumerate every named clause / link / assumption from Step 2.
2. For each, locate the code line(s) that implement the discharge. Use grep on related identifiers.
3. Mark each entry as `discharged`, `partial`, or `gap`.

**Deliverable table**:

| Clause | Expected discharge | Actual code line | Status |
|---|---|---|---|
| §3.2 B8(a) attestation verifies | `verify_attestation(report)` returning Err on invalid | `crates/contract/src/handle.rs:201` checks envelope length only | gap |
| §3.2 B8(c) image registered | `EnclaveImageRegistry.contains(image)` check | `crates/contract/src/handle.rs:218` | discharged |
| §8.7 link 5 chain verifies proof | gnark public-input verification on chain | `crates/contract/src/handle.rs:240` rejects with "not yet implemented" | gap |
| §6.3 dstack_kms_trust enclave_pubkey provenance | provenance-binding check at registration | not in code | gap |

**Worked example**: verified-rcv `C2` (envelope-only verification) and `C3` (enclave_pubkey provenance missing) and `N1` (gnark verification deferred) were all AB.2 misses. The intent clearly stated each obligation; the code did not discharge it. AB.2 applied internally would have produced all three as `gap` rows.

### AB.3 — Deferred-is-panic

For every branch in production code (default features, release profile) that is labeled deferred, stub, mock, TODO, "not yet implemented", `unimplemented!`, `todo!`, or "Mock", confirm the branch panics or returns `Err`.

**Procedure**:

1. Grep for `unimplemented!`, `todo!`, `TODO`, `FIXME`, `Mock`, `mock_`, `_stub`, `not yet implemented`, `deferred`, `placeholder`, `panic!`.
2. For each hit in production code (NOT in `#[cfg(test)]` or behind a non-default feature flag), determine what the branch does on the happy path.
3. Flag any branch that returns `Ok`, the default value, or proceeds silently.

**Deliverable table**:

| Branch | Site (file:line) | Production-default? | Behavior | Verdict |
|---|---|---|---|---|
| `Mock` attestation variant | `crates/contract/src/attest.rs:54` | yes (default features) | returns `Ok(())` | UNACCEPTABLE — must panic or be gated behind explicit feature |
| `real_zkdcap_verify` stub | `crates/zkdcap/src/lib.rs:30` | yes | returns `Err("not yet")` | acceptable (explicit Err) |

**Worked example**: verified-rcv `C1` (Mock variant accepted as Ok) and `N11` (real-zkdcap stub returning Err) are both AB.3 surface. C1 was the unacceptable case (silently Ok); N11 was the acceptable case (explicit Err). The lens distinguishes the two.

### AB.4 — Who-controls

For every field of stored state, name the supplier and the validation applied at the storage point.

**Procedure**:

1. Walk the code's storage schemas (Maps, Items, structs that are persisted).
2. For each field, name who supplies the value at the storage write site (admin tx, user tx, derived from other state, chain context).
3. For each admin-supplied field, name the validation. For each user-supplied field, name the access control + validation.

**Deliverable table**:

| Field | Supplier | Validation | Gap |
|---|---|---|---|
| `EnclaveImageRegistry.entry.pubkey` | admin (`UpdateImageRegistry` tx) | none (admin trusted to supply correct pubkey) | trust boundary admits admin pubkey-substitution; downstream layers cannot detect |
| `EnclaveImageRegistry.entry.mrtd` | admin | hex-string only, no length pin | shape validation absent |
| `Election.ballots[]` | user (`SubmitBallot` tx) | encrypted, accepted as-is | by-design (ballots are user-supplied) |

**Worked example**: verified-rcv `N2` (admin picks pubkey freely) is AB.4 surface. `M3` (mrtd length unpinned) is AB.4 + field-spec. The admin column makes the trust boundary explicit and surfaces every place "we trust the admin" silently widens the attack surface.

### AB.5 — API field-name fidelity

For every JSON, protobuf, borsh, or other public-API field, confirm the value placed at the field carries the semantic the field name implies.

**Procedure**:

1. List every public API surface: query response structs, event types, message payloads, exported JSON schemas.
2. For each field, read the field name and the code that populates it.
3. Compare the semantic the name implies (e.g., `mrtd_hex` implies "the MRTD TDX measurement, hex-encoded") to the value actually placed there (e.g., a compose-hash, or an empty string, or a different measurement).

**Deliverable table**:

| API surface | Field | Name implies | Value populated | Gap |
|---|---|---|---|---|
| `EnclaveStatusResponse` | `mrtd_hex` | TDX MRTD measurement | `compose_hash` value | API-presentation-drift |
| `EnclaveStatusResponse` | `tcb_status` | TCB evaluation result | empty string in current build | gap (must populate or remove from API) |

**Worked example**: verified-rcv `M5` (compose_hash in mrtd_hex slot) is the canonical AB.5 finding. The contract returned an MRTD-shaped field whose value was the wrong measurement. The lens compares name-to-value field by field.

### AB.6 — Deferral-justification audit

For every deferred finding from a prior audit round, decompose the stated deferral justification into refutable claims and audit each.

**Procedure**:

1. Read prior audit reports under `<project>/.colosseum/audit/`. Note every finding marked "deferred" or "acceptable risk for now".
2. For each deferral, extract the justification's claims as a numbered list.
3. For each claim, evaluate whether it actually holds in the current code.

**Deliverable table**:

| Deferred finding | Justification claims | Claim audit | Verdict |
|---|---|---|---|
| Prior R3's deferral of N2 timelock | (1) N2 timelock prevents adversarial pubkey rotation; (2) prior R2's registration-ReportData fix binds registration | Claim 1: timelock applies to registry rotation, not to first registration. Claim 2: registration ReportData binds the pubkey, not the registration address. | Wrong-deferral — replay of valid registration quote across registrations is still possible |

**Worked example**: verified-rcv `N13`/`N22` surfaced in R3/R4 from a wrong deferral of `N2`. The R3 auditor accepted "N2 timelock makes this acceptable" without auditing the claim. The deferral was wrong: the timelock applied to a different code path than the attack required. AB.6 applied internally to R3's own deferral would have caught this in R3 instead of R4.

## Step 4: Synthesize the finding list

Aggregate the six lens tables into a finding list. Each finding gets:

- **ID** — `CA-<NN>` (CA for code-adversarial)
- **Lens** — AB.1 / AB.2 / AB.3 / AB.4 / AB.5 / AB.6
- **Severity** — Critical / Major / Minor / Informational
- **Surface** — contract / runtime / cross-layer / spec / build-pipeline
- **Intent reference** — the §X.Y clause this discharges or violates
- **Code reference** — file:line
- **Summary** — one paragraph
- **Recommended fix** — concrete edit pointer (NOT the fix itself — you do not write code in this stage)

Order findings by severity descending, then by lens (AB.1 first, AB.6 last).

## Step 5: Persist the deliverable

Write to `<project>/.colosseum/code-adversarial/<ISO-date>-<operator>.md`. Format:

```markdown
# Code-adversarial review: <project>  —  <ISO-date>

- Operator: <agent identity, e.g. "Claude Opus 4.7 via Claude Code session B (NOT the implementation author)">
- Code commit reviewed: <git rev-parse HEAD>
- Intent version reviewed: <intent's frontmatter version>
- Ledger version reviewed: <ledger's frontmatter timestamp>
- Lenses applied: AB.1 through AB.6

---

## AB.1 — Commitment-coverage

<table from Step 3>

## AB.2 — Clause-to-line discharge

<table>

## AB.3 — Deferred-is-panic

<table>

## AB.4 — Who-controls

<table>

## AB.5 — API field-name fidelity

<table>

## AB.6 — Deferral-justification audit

<table>

---

## Finding list (consolidated)

| ID | Lens | Severity | Surface | Intent ref | Code ref | Summary | Fix |
|---|---|---|---|---|---|---|---|
| CA-01 | AB.1 | Major | cross-layer | §2.5 | crates/contract/src/serialize.rs:42 | chain_id missing from canonical_serialization | add chain_id and contract_address to canonical_serialization input |
| ... |

## Summary

- Total findings: <N>
- By severity: Critical=<C> Major=<M> Minor=<m> Informational=<i>
- By lens: AB.1=<n1> AB.2=<n2> AB.3=<n3> AB.4=<n4> AB.5=<n5> AB.6=<n6>
- Recommended next step: <patch list ordered by severity, then by intent-cited > code-only>
```

## Step 6: Report to the user

After persisting, report:

- One-line summary: `Code-adversarial pass: N findings (C Critical, M Major, m Minor, i Informational). Lens breakdown: AB.1=n1 ... AB.6=n6.`
- Absolute path to the deliverable
- Top three highest-severity findings by ID + one-line summary
- Recommended next step: revise intent / code / both per finding fix recommendations, then re-run if the changes touch any clause cited by a finding

## When to invoke

- AFTER code-implementation produces a commit (every non-trivial commit; minor refactors that touch no intent clause may skip)
- BEFORE external audit
- Whenever a prior code-adversarial round's findings have been addressed and re-application is warranted (treat as Round N+1; deliverable name carries the round number)
- After a major spec revision that propagates to code (Step 5 of `colosseum-change`)

## Acceptance criteria

- All six lenses applied, even if one produces an empty table (empty table is meaningful — say "AB.X — no commitments / no admin-supplied fields / etc." explicitly)
- Every finding has both an intent reference AND a code reference
- The operator identity is recorded and is distinct from the code-implementation author
- The deliverable file exists at the canonical path
- The finding list is consolidated (not just six disjoint tables) so downstream stages (audit, fix work, re-verification) can plan from one ordered list

## Output deliverable

`<project>/.colosseum/code-adversarial/<ISO-date>-<operator>.md` per the Step 5 format. This file is the load-bearing artifact; the user-facing summary is a courtesy.

## What you do not do

- You do not write or edit code. Findings name the fix; you do not apply it.
- You do not soften severities to make the project look healthier. AB.1 gaps that allow cross-deployment replay are Major, not Minor.
- You do not skip lenses. If AB.5 produces no findings, write "AB.5 — no API surface fields with name-implies-semantic drift" and move on.
- You do not run this stage on a project with no intent document. Without intent, the lenses anchor on nothing.
- You do not accept "the implementation author already knows the gap" as a reason to skip a lens. The deliverable is the record; verbal awareness does not count.

## Spirit

External audit is the methodology's final adversary. The cost of relying on it as the *first* adversary against the implementation is high: cascade rounds (verified-rcv had `C2` open in R1 and R2; `C3` open in R1, R2, and R4), defer-then-rescind cycles, and findings the methodology was structurally capable of catching but didn't because no stage looked. The six lenses encode the failure modes external auditors actually exploit. Apply them internally, then the audit's job is to find what the lenses missed — which is a much smaller surface, and which is what an external audit is actually useful for.
