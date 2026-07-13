---
name: colosseum-boundary
description: Decompose a system into component intents with assume/guarantee boundaries so the panel can verify each component independently and compose the results into one system verdict. Reached from colosseum-reverse-intent when a distilled system is too large for one intent document; consumes C6's PROVISIONAL non-goals rule at each boundary. Produces a system-intent document (templates/system-intent.template.md) plus per-component intent docs, and defines how component verdicts aggregate under G2 and how the change loop re-verifies only the affected components. Use when a target is a system of parts (services, crates, modules) whose trust claim no single component makes alone.
---

You are decomposing a **system** into component intents joined by explicit assume/guarantee boundaries. A single intent document (colosseum-intent) anchors one coherent surface. When the target is larger than that (multiple services, crates, or bounded subsystems that call each other), one document either sprawls or silently swallows the interfaces where the real bugs live. This skill splits the system at those interfaces and makes each interface a checkable contract.

This is scaffolding for a system-of-intents run (for example, a brownfield service like bidboard entering the methodology through colosseum-reverse-intent). The run itself dispatches the adversarial panel and the verification pyramid per component; this skill produces the documents and the composition rules that run depends on. It does not itself verify anything.

## When this skill applies

Use it when all of these hold:

- The target is more than one coherent surface. A single crate with one public API is a `colosseum-intent` job, not this.
- Components interact across a boundary you can name: an API, a message schema, a shared invariant, a call contract.
- No single component's verification, on its own, backs the property you actually care about. The property is a composition of component guarantees.

If the target is one surface, stop and use `colosseum-intent` (forward) or `colosseum-reverse-intent` (backward). Over-decomposing a small system buys interface bookkeeping for no assurance.

## Entry from reverse-intent

The common path in is `colosseum-reverse-intent`: a system already runs and its intent is implicit in code. When that skill's Step 1 target-scope question answers "this is several subsystems, not one," it hands off here rather than forcing every subsystem into one distilled document.

Carry C6's rule across the boundary unchanged. Reverse-intent marks every inferred non-goal `PROVISIONAL:` until the user confirms it, because absence of code is evidence the team never got to something, not evidence they excluded it. At a component boundary the same discipline applies to the boundary itself: an assumption a component appears to make about a neighbor, read off the code, is `PROVISIONAL:` until the composed system-intent confirms that some neighbor actually guarantees it. A `PROVISIONAL:` boundary assumption is a gate, not a formality. It does not become a committed `A*` clause by defaulting through; it converts only on confirmation, or it becomes a `TBD:` open question naming what is unresolved. A downstream spec author must never encode an unconfirmed cross-component assumption as a hard boundary.

## Identifying component boundaries

Walk the system and cut where coupling is thinnest and the contract is nameable:

- **Call boundaries.** One component invokes another through a typed interface. The caller assumes a postcondition; the callee guarantees it.
- **Data boundaries.** Components share a schema or a serialized message. The producer guarantees the schema's invariants; the consumer assumes them.
- **State boundaries.** A shared invariant that two components both touch. One component's transitions preserve it (guarantee); the other's depend on it (assume).
- **Trust boundaries.** A component treats another as trusted or untrusted. This is a `K*` trust assumption at the system level; record it, do not bury it.

For each boundary, name the two sides and the single property crossing it. If you cannot state the crossing property in one sentence, the cut is in the wrong place. Move it until you can.

## Assume/guarantee clause discipline (A* / G*)

Each component in the system-intent carries two clause families with stable IDs:

- **`A*` (assume)** — what this component takes as given about its environment and its neighbors. An `A*` clause is not something this component checks; it is something a neighbor must deliver or a `K*` trust assumption must cover.
- **`G*` (guarantee)** — what this component promises to its neighbors when its own `A*` assumptions hold. A `G*` is discharged by that component's own verification evidence (a G1 record keyed to the component's intent).

Discipline:

1. Every `A*` clause MUST be discharged by some neighbor's `G*` clause or by an explicit system-level `K*` trust assumption (with a waiver, per G2). An `A*` clause with nothing on the other side is an open hole in the system, not a verified boundary. List it as an unresolved composition obligation, never as satisfied.
2. A `G*` clause is only as strong as the `A*` clauses it rests on. When you cite a component's guarantee as discharging a neighbor's assumption, the neighbor inherits that component's unmet assumptions transitively. Track the chain.
3. `A*` and `G*` IDs live in the system-intent document's own ID space. Do not confuse a system-intent `A*` (assume) clause with a component intent's Section 3.4 `A*` encoding-discipline note; the two never appear in the same document, but keep the distinction explicit when you cross-reference.
4. ID retirement discipline carries over from the intent template: once assigned, an `A*` or `G*` ID is never reused, even after the clause is removed. Downstream ledger records key on these IDs.

## Composing component verdicts under G2

The system verdict is a function of the component verdicts and the boundary obligations, computed under the same G2 truth table the rest of the methodology uses. Do not invent a softer rule for systems.

- The system is `VERIFIED[scope]` only when every component is `VERIFIED[scope]` for its required clauses **and** every `A*` assumption is discharged by a matching `G*` guarantee or a waived `K*` assumption. The system scope string names the profile and every waived or externally-assumed boundary, exactly as a single-component scope does. Never emit a bare `VERIFIED`.
- The system is `FAILED` if any component is `FAILED`, or if a boundary is contradicted (a component's `G*` provably does not deliver what a neighbor's `A*` requires).
- The system is `INCOMPLETE` if any component is `INCOMPLETE`, or if any `A*` assumption has no discharging `G*` and no waived `K*`, or if the required-component list is empty. An undischarged assumption is `INCOMPLETE`, not a pass. This is the composition analogue of the single-component rule that an unwaived externally-assumed claim cannot PASS.

Record the composition itself as a G1 evidence record whose `required_targets` are the boundary obligations (the `A*`-discharged-by-`G*` pairs), so the system verdict is auditable the same way a component verdict is. Use `colosseum-compose` to maintain the integration ledger that holds these records.

## Incremental re-verification in the change loop

The point of assume/guarantee decomposition is that a change to one component does not force re-verifying the whole system. When a component changes, re-verify only:

1. That component (its own source changed, so its G1 records are stale by `source_snapshot`).
2. Any component whose `A*` assumptions were discharged by a `G*` clause of the changed component **that changed meaning**. If the changed component's guarantees are byte-identical in effect, its neighbors' assumptions still hold and their evidence is reusable.

A component's evidence is reusable across a system change exactly when its own `source_snapshot` binding is unchanged and every `A*` it depends on is still discharged by an unchanged `G*`. The ledger version fields (see docs/incremental-reverification.md) and the per-record `source_snapshot` bindings are what let you compute this reuse safely rather than re-running everything out of caution. Enter the change through `colosseum-change`, which triages intent-touching versus implementation-only edits; this skill supplies the blast-radius rule it uses at a boundary.

## Non-Rust components

Components need not share a language or a tool. The assurance profiles (tested / bounded / proved) are tool-agnostic contracts on evidence strength, not Rust-specific. A component in another language backs its `G*` clauses with whatever tool reaches the required profile for that language (see docs/incremental-reverification.md for the tier mapping). The composition rule is unchanged: the boundary is a property, and either some component's guarantee discharges it at the required profile or it stays an open obligation.

## Output

1. A system-intent document at the user's chosen location, authored from `templates/system-intent.template.md`: system identity and version, the component list, per-component `A*`/`G*` clauses, the composition graph (which `G*` discharges which `A*`), system-level invariants and `K*` trust assumptions, and the ledger schema version field.
2. A per-component intent document for each component (via `colosseum-intent` or `colosseum-reverse-intent`), so each component's own clauses have stable IDs the system-intent's `A*`/`G*` clauses can cite.
3. An explicit list of undischarged boundary obligations. These are the composition's open questions; the system cannot be `VERIFIED` while any stands.

Do not save a system-intent with a `PROVISIONAL:` boundary assumption still standing as if committed, and do not record a system verdict better than G2 permits given the undischarged obligations.
