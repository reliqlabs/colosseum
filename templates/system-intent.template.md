<!--
  Colosseum system-intent template (M5).

  A system-intent joins several component intents at explicit assume/guarantee
  boundaries. Author it with the colosseum-boundary skill. Each component still
  gets its own intent document (colosseum-intent / colosseum-reverse-intent);
  this document names the components, states the cross-component A*/G* contracts,
  and records how the component verdicts compose into one system verdict under G2.

  Fill every <angle-bracket> placeholder. Delete this comment before committing.
-->

# System Intent: <System Name>

- **Ledger schema version:** colosseum-ledger/v1
- **System version:** v0.1.0
- **Status:** DRAFT | REVIEWED | COMMITTED
- **Composition profile:** tested | bounded | proved

The ledger schema version is the `ledger_schema_version` field every G1 record
set (envelope) for this system is written under (see
docs/incremental-reverification.md). It is recorded here so a change-loop pass
can detect a schema migration, not only a source change.

## Version History

Same discipline as the component intent template. A change to any `A*`/`G*`
clause's meaning, or to the composition graph, is a **MAJOR** bump. A new
component, a new `A*`/`G*` clause, or a newly discharged obligation is **MINOR**.

**ID retirement discipline:** once assigned, a component ID (`C*`), an assume
clause ID (`A*`), or a guarantee clause ID (`G*`) is never reused, even after
removal. Downstream ledger records and the compose ledger key on these IDs.
List removed IDs under **Retired**.

### v0.1.0 — <date> — initial draft
- Initial decomposition.

## 1. System Identity

- **Name:** <system name>
- **Scope:** <what surface the system covers; what is explicitly outside it>
- **One-sentence purpose:** <what the system does, as a whole>
- **Entry skill:** <colosseum-reverse-intent (brownfield) | colosseum-intent (greenfield)>

## 2. Components

One row per component. Each component has its own intent document; cite it by path.

| ID | Component | Intent doc | Language / tool | Required clauses | Profile |
|----|-----------|-----------|-----------------|------------------|---------|
| C1 | <name>    | <path>    | <e.g. Rust / Kani> | <e.g. B1,B2,S1> | <tested\|bounded\|proved> |
| C2 | <name>    | <path>    | <e.g. Go / proptest> | <...> | <...> |

"Required clauses" are the component-intent clause IDs the composition depends
on. A component may prove more than the system needs; only the listed clauses
are load-bearing for this system's verdict.

## 3. Assume clauses — `A*`

What each component takes as given about its neighbors or environment. An `A*`
clause is NOT checked by the component that holds it; it must be discharged by a
neighbor's `G*` (Section 4) or by a system `K*` trust assumption (Section 6).

Note: this `A*` space (assume) is distinct from a component intent's Section 3.4
`A*` encoding-discipline notes. They never share a document.

| ID | Held by | Assumes | Discharged by |
|----|---------|---------|---------------|
| A1 | C2 | <e.g. "every message from C1 carries a valid signature"> | G1 |
| A2 | C1 | <e.g. "the store never returns a partial write"> | G3 |
| A3 | C1 | <e.g. "the OS RNG is unpredictable"> | K1 (waived) |

Every `A*` row's "Discharged by" cell MUST name a `G*` clause or a `K*`
assumption. A blank cell is an open composition obligation (Section 7), not a
satisfied assumption.

## 4. Guarantee clauses — `G*`

What each component promises its neighbors when its own `A*` assumptions hold.
A `G*` is discharged by that component's own G1 evidence (a record keyed to the
component intent's required clauses).

| ID | Provided by | Guarantees | Rests on (A*) | Backing clause(s) |
|----|-------------|-----------|---------------|-------------------|
| G1 | C1 | <e.g. "every emitted message is signed"> | (none) | C1:B2 |
| G3 | C3 | <e.g. "writes are atomic"> | A5 | C3:S1,B4 |

"Backing clause(s)" cite the component-intent clause IDs whose G1 records
substantiate the guarantee. "Rests on" names the holder's own `A*` assumptions
the guarantee is conditional on; those propagate transitively to any neighbor
this `G*` discharges.

## 5. Composition graph

State, as a list of edges, which guarantee discharges which assumption. This is
the spine of the system verdict.

- `G1 (C1) ⟶ A1 (C2)` : <one line on what crosses this boundary>
- `G3 (C3) ⟶ A2 (C1)` : <...>

For each edge confirm the guarantee is at least as strong as the assumption it
discharges. A `G*` weaker than the `A*` it is claimed to satisfy is a contradicted
boundary and makes the system `FAILED`, not `INCOMPLETE`.

## 6. System invariants and trust assumptions

### 6.1 System-level invariants

Properties true of the composed system that no single component states alone.
Give each a stable ID (`SI*`) and name the component guarantees it emerges from.

- `SI1` — <e.g. "no message is processed twice"> — emerges from G1, G4.

### 6.2 Trust assumptions — `K*`

Out-of-model assumptions the whole system rests on: things no component's
verification checks (off-chain honesty, cryptographic hardness, external-service
correctness). Each `K*` that discharges an `A*` clause requires an explicit
waiver in the ledger, per G2, and surfaces in the system scope string.

- `K1` — <e.g. "the OS RNG is unpredictable"> — discharges A3.

## 7. Open composition obligations

Every `A*` clause with no discharging `G*` or waived `K*`. The system cannot be
`VERIFIED` while any obligation stands; each keeps the system `INCOMPLETE`.

- <A-id> held by <component>: <what is unmet, and why no guarantee covers it yet>

If this section is empty and every component is `VERIFIED[scope]`, the system is
eligible for `VERIFIED[scope]`; otherwise it is `INCOMPLETE` (undischarged
obligation or an `INCOMPLETE` component) or `FAILED` (a `FAILED` component or a
contradicted boundary edge).

## 8. System scenarios

Concrete end-to-end sequences that cross at least one boundary, so the
composition graph has witnesses. Each scenario names the components and the
`A*`/`G*` edges it exercises.

### 8.1 <Scenario name>
- **Components:** <C-ids>
- **Boundaries exercised:** <edges from Section 5>
- **Sequence:** <step-by-step; where each guarantee is relied on>
- **Expected system outcome:** <observable result>

## Open Questions

- `TBD:` <unresolved boundary; a demoted PROVISIONAL assumption, per C6>
