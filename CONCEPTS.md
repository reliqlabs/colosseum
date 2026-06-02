# Colosseum concepts

The names and ideas this methodology uses. Authoritative; SKILLs and docs use these terms.

## The five pillars

The five complementary trust mechanisms Colosseum composes. Always referred to by name, not number.

| Pillar | What it does |
|---|---|
| **Formal verification** | Mechanistic proofs; real guarantees, not statistical confidence |
| **Adversarial generation** | One model produces, another attacks. Adversaries beat consensus for correctness work |
| **Substrate constraints** | Types, ownership, linters, sanitizers — cheap, deterministic, deny whole bug classes |
| **Empirical validation** | Property tests, fuzzing, bounded model checking — covers regions formal methods can't reach |
| **Boundary discipline** | Narrow trusted/untrusted interfaces; verified core, contained periphery |

## The verification pyramid

Cheap to expensive, exec and spec axes. Each property routes to the cheapest tool that can verify it.

**Exec axis** (against real Rust, cheap → expensive):
Types → Lints → Property tests → Fuzzing → Kani → Verus → Aeneas → Lean

**Spec axis** (upstream of code, when system-level reasoning matters):
Quint / TLA+ → Lean (math, refinement)

## The workflow

Ten stages. Each stage produces an artifact that anchors the next.

1. **Intent doc** — human-written source of truth
2. **Tracer prototype** — fast throwaway, proves the design is feasible
3. **Intent revision** — informed by tracer
4. **System spec** — Quint/TLA+ when distributed semantics matter
5. **Implementation spec** — Lean specs and/or Verus annotations
6. **Spec adversarial review** — multi-model attack on each spec draft
7. **Implementation** — Rust against validated specs
8. **Verification** — the pyramid runs continuously
9. **Failure classification** — spec wrong / code wrong / prover stuck
10. **Coverage dashboard** — per-function trust calibration

Steps are sequential; later additions get *names*, not fractional numbers. If a step gets inserted between two existing steps, it earns a real name and a real position.

## The SKILLs

The verbs you actually run. Each is a SKILL the harness can invoke.

| SKILL | Verb | Stage |
|---|---|---|
| `colosseum-intent` | Author an intent doc forward (elicitation) | 1 |
| `colosseum-reverse-intent` | Distill an intent doc from existing code | 1 (retro) |
| `colosseum-adversarial` | Run spec adversarial review with intent + Quint trace generation | 6 |
| `colosseum-code-adversarial` | Read implementation against intent through six lenses | between 7 and 8 |
| `colosseum-lifecycle-adversary` | Red-team multi-tx admin features against Quint | when contract gains admin features |
| `colosseum-verify` | Run the verification pyramid | 8 |
| `colosseum-compose` | Maintain cross-component trust ledger with code-line citations | 8 (continuous) |
| `colosseum-change` | Upstream-first change loop with re-verification | when changing a spec'd project |

## The trust ledger

A project's `.colosseum/ledger.md` records every cross-component trust claim with:
- the named theorem
- the tools that contribute (Quint property, Lean theorem, Verus annotation, Kani harness)
- code-line citations for each link
- axiom inventory (which axioms each theorem's closure depends on)

`colosseum-compose` maintains it. CI gates fail when a link drifts from executable code.

## Trust-assumption categories

Each axiom in a project's trust closure falls into one of these. Always referred to by name.

| Category | What it means |
|---|---|
| **Standard cryptographic assumption** | Reduces to a textbook primitive (EUF-CMA, DDH, collision resistance, etc.) |
| **Deployment-side commitment** | Deployer-side runtime obligation (collateral freshness, rotation, well-formedness) |
| **Parser-layout assertion** | Pins a parser output to a specific window of input bytes; cross-checked against production code |
| **Bundled trust boundary** | Multiple primitives wrapped into one axiom for convenience; cleanup target |
| **Over-strength** | Asserts more than reality warrants; usually a refactoring target |
| **Impossibility / vacuity** | Assertion holds vacuously or asserts the impossible; bug |
| **External module dependency** | Trust assumption supplied by an upstream component, named explicitly |
| **Lean standard** | `propext`, `Classical.choice`, `Quot.sound` — accepted ambient |
| **Predicate carrier** | Opaque predicate with no asserted truth value; bookkeeping only |
| **Completeness** | The verifier accepts genuinely valid inputs; typically the dual of soundness |

The first four are the ones cleanup work moves *toward* (named primitives, named commitments, narrow assertions). The next two are what cleanup moves *away from*.

## Adversarial review findings

Findings are tagged inline with severity:

- **Critical** — soundness gap, allows attacks past the verifier
- **High** — audit-transparency gap, misleads reviewers about what's trusted
- **Medium** — methodology / framing tightening
- **Low** — cosmetic / docstring honesty

Inside a single review, findings are numbered (Critical 1, Critical 2, High 1, ...). Across reviews, findings are referred to by the practice they targeted (e.g., "the `signed_by_qe` decomposition critique") rather than by review-internal labels.

## Naming rules

Three rules to keep the namespace cheap to learn.

1. **No cycle numbers.** Git commits are the chronology. Commit messages carry the descriptive title. There is no "Cycle 7.5" — there is the commit whose title is "axiom demotion via DCAP reference verifier".
2. **No fractional steps.** A step inserted later gets a name, not `Step 4.5`. If the name doesn't fit, the step shape was wrong.
3. **No alphabetical asks.** Methodology improvements live in `methodology-improvements.md` under their practice name (e.g., "system-of-intents shape", "per-section adversarial dispatch", "ghost-variable encoding"). Historical letter labels (Ask A, Ask AB) remain in archive only.

## Where the historical labels live

For traceability only — never load-bearing for new work.

- `archive/` — old MEMORY snapshots, retired skill versions
- `methodology-improvements.md` — current improvements; previous "Ask X" labels appear in a single archive table at the end mapping old label → current practice name
- Per-project `.colosseum/ledger.md` — frozen historical artifacts (e.g., Quartz's `Cycle 7.x` ledger entries) — stay as-is; they are the audit trail
