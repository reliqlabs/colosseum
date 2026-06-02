# Methodology improvements

Improvements to the Colosseum methodology, organized by practice. Each entry names what changes, why it's needed, and where it lands in the SKILLs / docs once stable. Vocabulary follows [CONCEPTS.md](./CONCEPTS.md): no ask-letter labels, no version-set numbering. Historical "Ask X" labels (from earlier methodology revisions) are preserved in [archive/methodology-asks-historical.md](./archive/methodology-asks-historical.md) for traceability only.

Each improvement carries a status:
- **shipped** — codified in a SKILL or doc; cite the location
- **pending** — exercised in a dogfood project but not yet codified
- **proposed** — backed by pattern survey or one-off observation; needs dogfood validation

External literature backing the proposals is in [references.md](./references.md). The dogfood projects that produced the evidence are named inline; their full evidence bases live in each project's `.colosseum/` directory.

---

## Adversarial review

### Multi-model dispatch infrastructure (shipped)

Multi-voice fan-out works through OpenCode CLI direct dispatch, with a gateway channel (kimi-k2-6, gpt-oss-120b, nemotron, etc.) as a first-class provider, per-route timeout caveats published as operational guidance, and LM Studio cross-session contention managed via `lms load` + retry-on-unload. The manifest protocol (`scripts/colosseum_run.py`) coordinates dispatch across harnesses. The synthesis phase uses an overlap-matrix format with theme clustering, voice-failure-mode catalog filtering, and voice diversity metadata (family + lineage + inference-seat) recorded per voice. *Lands in:* `skills/colosseum-adversarial/SKILL.md` Step 4 + Step 7. Reference dispatch scripts in `verified-rcv/.colosseum/scripts/*_dispatch.py`.

### Theorem-prover specialist exclusion (shipped)

Goedel-class and other theorem-prover specialist models are excluded from adversarial spec review — they pattern-match the spec as a proof goal and attempt tactics rather than attack it. *Lands in:* `skills/colosseum-adversarial/SKILL.md` "Excluded model classes" paragraph. Same models remain useful at the verify-pyramid layer (`mcp__goedel__propose_lean_tactic`).

### `--variant high` (or reasoning-effort flag) as default for spec-class adversarial work (shipped — should default everywhere)

Reasoning models at default effort produce shallower critiques. Tautological-shadow detection in particular benefits from extra reasoning budget — the failure mode is "predicate typechecks and reads as substantive but does no work," which requires the reviewer to actually evaluate what the predicate says, not just that it parses. Verified-rcv evidence: cross-critique, defense, and re-cross-critique rounds all dispatched at `--variant high` produced non-trivial findings (tautological-shadow detection, scope-name overstating, state-space coverage hole) where default-effort runs missed them. *Lands in:* `skills/colosseum-adversarial/SKILL.md` Step 4 dispatch table + manifest schema. Provider-specific equivalents: Anthropic `thinking.budget_tokens`, OpenAI `reasoning.effort`, Google `thinking.thinking_budget`, NVIDIA `extra_body.reasoning_effort`.

### Cross-critique as standard post-fan-out step (shipped)

After fan-out + synthesis produces a candidate canonical, dispatch a cross-critique round where each voice reviews *another* voice's spec against a structured Q1/Q2/Q3 prompt (does each predicate encode the intent's claim or is it tautological; are there state-space gaps; single most material remaining concern). Synthesis aggregation alone misses tautological-shadow defects (`val foo_shadow = true`, vacuous bounds) because each voice can fall into the same trap; cross-voice review breaks the symmetry. Verified-rcv evidence: cross-critique caught tautological S9 shadow and B8 tautology that v11 synthesis alone missed. *Lands in:* `skills/colosseum-adversarial/SKILL.md` with reference Q1/Q2/Q3 prompt template.

### Defense round for canonical-defect adjudication (shipped)

When cross-critique surfaces a non-trivial defect claim, dispatch a defense round before applying fixes. Voices: canonical's author + one of the original critics + a third independent voice. Each voice must explicitly defend / concede / propose-third-option with reasoning. Near-unanimous concede mandates the fix. Verified-rcv evidence: defense voices at `--variant high` produced honest concessions with reasoning ("the predicates as stated are bounds, not the intent's claim"), no anchoring observed. *Lands in:* `skills/colosseum-adversarial/SKILL.md` after the cross-critique step. Reference dispatch: `verified-rcv/.colosseum/scripts/critique_and_defense_dispatch.py`.

### Re-cross-critique after canonical revision (shipped)

After applying fixes from cross-critique + defense, run a re-cross-critique round before accepting the revision. Same Q1/Q2/Q3 harness with "is the fix structurally sound?" prepended. Verified-rcv evidence: re-cross-critique caught two defects introduced by the canonical revision itself (a `bt_tallied = oneOf(Set(0,1,2,3,5))` coverage hole; `is_tally_spec_output` name overstating its scope). Without re-cross-critique both regressions would have shipped silently. Mandatory whenever the revision touches a load-bearing predicate or invariant. *Lands in:* `skills/colosseum-adversarial/SKILL.md` after the defense step. Reference dispatch: `verified-rcv/.colosseum/scripts/revised_canonical_critique.py`.

### Quint-adversarial as separately-run trace generation (shipped)

Quint-spec construction produces invariants but does not by itself produce attack traces. The adversarial pass against the Quint model is a separate methodology step from spec construction: every Quint property gets an adversarial-trace generation pass. Output: a list of admissible trace prefixes that would violate the property if uncaught, cross-referenced to code enforcement. Verified-rcv evidence: `quint run --invariant inv_b1_tally_write_once` would have produced the trace `[CreateElection, SubmitBallot, CreateElection]` and caught the missing phase check in the contract before audit. *Lands in:* `skills/colosseum-adversarial/SKILL.md` Step 5 (Quint-adversarial).

### Lifecycle-adversary stage for multi-tx admin features (shipped)

Any contract revision that adds a new admin transition, a timelock, a multi-tx Propose/Finalize/Cancel feature, or a state archival triggers a lifecycle-adversary stage. The operator extends the Quint model with the new transitions, then Quint-adversarial generates counterexample traces against active-phase invariants over all multi-block sequences combining the new transitions with existing ones. Verified-rcv evidence: a registry-rotation timelock landed without the Quint model being extended; the auditor found a multi-tx DoS sequence that a lifecycle-adversary pass would have caught at landing. *Lands in:* `skills/colosseum-lifecycle-adversary/SKILL.md`.

### Code-adversarial as a first-class stage with six named lenses (shipped)

After code-implementation produces a commit and before audit, an internal red-team agent (distinct from the code-implementation author) applies six lenses to the implementation referencing intent and ledger: commitment-coverage, clause-to-line discharge, deferred-is-panic, who-controls, field-name fidelity, deferral-justification audit. Verified-rcv evidence: 8 of 13 high-severity audit findings across 4 rounds would have been caught by an internal code-adversarial stage with these six lenses applied to the implementation against the intent. *Lands in:* `skills/colosseum-code-adversarial/SKILL.md`.

### Per-section adversarial dispatch (proposed)

Model reliability degrades non-monotonically as input length grows (Chroma "Context Rot" research + ∞Bench / LoCoBench / BABILong benchmarks). Per-section dispatch keeps each voice call in the reliable context range. Each voice receives `(system_prompt, target_section, cross_section_summary, brief)` instead of `(system_prompt, full_intent, brief)`. Cost: N×M calls. Benefit: each call fits cleanly in budget; voice attention is not diluted. *Dogfood needed:* any project with intent > 50K tokens. *Lands in:* `skills/colosseum-adversarial/SKILL.md` Step 4 as an alternative dispatch mode + `scripts/colosseum_run.py` adds `--per-section` mode. External references: [references.md](./references.md) Section C.

### File-access subagent dispatch (proposed)

OpenCode's native subagent architecture with `permission.read: allow` lets a subagent read what it needs on demand rather than receiving an inlined prompt. Current default (inlined-everything) forces every voice to ingest the entire intent doc each time, even if only one section matters. File-access subagents read just-in-time and bound their own attention. *Dogfood needed:* any project run via OpenCode + Claude Code dual-harness using the `colosseum_run.py` manifest protocol. *Lands in:* `skills/colosseum-adversarial/SKILL.md` Step 4 as the recommended shape for intent > 25K tokens or boundary-doc reviews.

### Frontier-tier requirement at scale (proposed)

For system-of-intents adversarial review at >100K effective context, mid-tier voices (mistral-119b, gemma-26b under 50K — both excellent in the ~25K range) are *complementary* but *not sufficient* in isolation. The methodology must be explicit: system-level adversarial review requires at least 3 frontier voices (Claude 4.x, Gemini 2.x/3.x, GPT-5.x, Kimi-k2.6, GLM-4.7). *Dogfood needed:* any system-of-intents project at frontier-tier scale. *Lands in:* `skills/colosseum-adversarial/SKILL.md` Step 4 with a named "frontier tier" model-id list (refreshed per release).

---

## Intent authoring

### System-of-intents shape (proposed)

For systems with 3+ components, a single monolithic intent doc is infeasible (~25K-token limits hit the Claude Code Read tool, reasoning-model output budgets, and gateway timeout caps for adversarial dispatch at long prompts). Decompose:

```
<system-repo>/
├── intent.md                          # SYSTEM intent (top-level claim, cross-component invariants, system trust boundaries)
├── components/
│   ├── <component-a>/.colosseum/intent.md
│   └── ...
├── boundaries/
│   ├── <component-a>--<component-b>.md
│   └── ...
├── decisions/
│   ├── ADR-001-...md
│   └── ...
└── .colosseum/
    └── compose-ledger.md
```

The DDD relationship patterns (Customer/Supplier, Open Host Service, Published Language, Anti-Corruption Layer, Shared Kernel) are the taxonomy for boundary-doc relationship classification. *Dogfood needed:* bidboard (next planned multi-component dogfood). *Lands in:* `skills/colosseum-intent/SKILL.md` with a system-of-intents decision tree; new `colosseum-boundary` skill for boundary-doc elicitation; `skills/colosseum-compose/SKILL.md` extended to track per-theorem intent-doc provenance. *Open question:* when to split — monolithic stays viable to ~25K tokens; system-of-intents kicks in at the 3rd component, regardless of token count. External references: [references.md](./references.md) Section A.

### Encoding-discipline notes as the convergence lever (shipped)

When fan-out voices diverge on the same encoding choice across regenerations, the divergence is not stochastic — it reflects under-specification in the intent. Re-running fan-out without changing the intent reproduces the divergence. The intent must be revised to constrain the encoding choice. Verified-rcv evidence: fresh-state regeneration on intent v0.3.1 did NOT converge voices on the same encoding axes that diverged previously; adding two encoding-discipline notes (enclave-layer state requirement for chain-side projection; snapshot-invariant requirement) DID move voice convergence on exactly those axes. Intent-tightening on encoding-discipline is the convergence lever; re-rolling the dice on the same intent is not. *Lands in:* `skills/colosseum-intent/SKILL.md` adds an "encoding-discipline notes" subsection; `colosseum-adversarial/SKILL.md` Step 7 synthesis searches for divergence-as-symptom-of-under-specification and proposes encoding-discipline-note candidates back to intent.

### Ghost-variable encoding for action-guard-only invariants (shipped)

When a behavioral invariant could be encoded as either action-guard OR ghost-variable+state-predicate, prefer the latter. Action-guard-only encoding takes the model checker out of the verification loop — nothing flags an action-set drift that bypasses the guard. Pattern: ghost variable captures the load-bearing state at the protected transition; state invariant checks the relation against the ghost; action-guard remains for liveness but is no longer load-bearing for safety. Verified-rcv evidence: re-cross-critique flagged a `tally_result monotone-once-set` invariant encoded only as `publish_result`'s action-guard `not(contract_tally_result.present)`. No state-side invariant would catch an action-set drift that bypassed the guard. The B2 invariant in v0.3.2 was correctly encoded as a ghost (`ghost_ballots_at_end_at` + `inv_b2_ballots_at_end_at_frozen`); the pattern should generalize. *Lands in:* `skills/colosseum-intent/SKILL.md` and (new) `colosseum-spec-encoding/SKILL.md` naming the preferred encoding pattern for freeze-at-time invariants.

### Field-spec discipline at intent-elicitation (proposed)

Intent prose can name a binary-data field by its semantic ("TDX measurement", "public key", "hash") without committing to a wire format. Downstream code then accepts malformed wire values. Intent-elicitation should produce a field-spec table for every binary-data field with columns `(field, semantic, wire format, length, validation site)`. Every field with a non-bounded length is flagged for explicit decision. Verified-rcv evidence: a Major finding where `mrtd` and `rtmr` were named as TDX measurements with no wire-length pin; the registry stored mrtd as an unbounded hex string. *Lands in:* `skills/colosseum-intent/SKILL.md` template adds a "Field specifications" section.

---

## Composition / ledger

### Per-conjunct failure-mode table is load-bearing (shipped)

The bundle cardinality of a security-lift theorem must be **derivable from the per-conjunct table** — specifically the count of `probabilistic-failure mode` rows — NOT pulled from axiom-closure size. Earlier Quartz work over-bundled 7 of 8 lifts because it derived cardinality from "how many axioms are in the classical-proof closure" rather than "how many conjuncts of the conclusion have an actual probabilistic-failure event". *Lands in:* `skills/colosseum-compose/SKILL.md` Step 3 dependency-entry template.

### Top-down Kani harness catalog from the trust-chain ledger (shipped)

Bottom-up Kani-harness catalog construction (start from "this struct is interesting; write a harness for it") produces a catalog that mirrors the prover's mental model rather than the trust-boundary surface. Verified-rcv evidence: shipped with 10 harnesses all targeting IRV result structure, zero targeting attestation verification, registry shape, gnark public_inputs construction, canonical_serialization byte layout, or ECIES decoder rejection paths. 6 of 13 high-severity findings lived on the uncovered trust-boundary surfaces. Top-down catalog: every link in the trust-chain ledger gets either a Kani harness named `<link_id>_<assertion>` or a closed-list `kani: skipped because <reason>` annotation. *Lands in:* `skills/colosseum-compose/SKILL.md` Step 5.

### Ledger-as-gate (code-line citations on every trust-chain link, shipped)

Ledger entries that name the right structure can drift from code because nothing forces reconciliation between ledger claims and executable code. Every link in the trust-chain ledger carries a `code: file:line` annotation pointing at the line that discharges the claim. For off-chain claims, the citation points to a testing harness, an external verifier, or an explicit `axiom: <reason>` annotation. CI runs a check: every link has a citation, every citation resolves to a non-empty line in the live codebase. Verified-rcv evidence: a Major finding surfaced when the ledger claimed "chain verifies proof" but the contract only checked envelope shape. The gate would have surfaced the gap at ledger-emission time. *Lands in:* `skills/colosseum-compose/SKILL.md` Step 3 dependency-entry template + Step 8 CI gate.

### Inter-component invariants via assume-guarantee reasoning (proposed)

Pairwise specs do not grow exponentially with component count when structured as assume-guarantee. Established theory (Dardik & Kang 2025; Liang/Feng POPL 2012 RGSim; CSim² TOPLAS 2021) shows the cost is O(n) component contracts + O(boundaries) handshake invariants + 1 conjunction theorem — linear, not exponential. Each component intent's invariants section is augmented with explicit *assume* clause (what the component requires of its environment) + *guarantee* clause (what it provides). The boundary doc records the implication-link: A.guarantee → B.assume. The compose-ledger records the system-level conjunction theorem. For N-ary interactions (3+ components in one invariant), escalate to a BIP-style n-ary interaction doc (Sifakis Verimag 2010). *Dogfood needed:* bidboard. *Lands in:* `skills/colosseum-intent/SKILL.md` adds the assume/guarantee structure when in system-of-intents shape; new `colosseum-boundary` skill walks the user through the implication-link. External references: [references.md](./references.md) Section B.

### Intent doc + boundary doc + spec versioning via SemVer (proposed)

Even without inter-component drift, single-component intent revisions need versioned identification for: audit trail, cross-reference stability (boundary docs reference component intents at specific versions), compose-ledger drift detection, debugging "which intent was this proof built against?".

| Artifact | Versioning |
|---|---|
| Intent doc | SemVer (MAJOR.MINOR.PATCH) |
| Boundary doc | SemVer + component-version pins (`compatible_with: { component-a: '>=0.3.0, <0.4.0' }`) |
| Formal spec (Quint / Lean) | SemVer; MAJOR bumps require refinement-theorem witness OR explicit breakage notice |
| ADRs | status-flag (proposed / accepted / superseded), no SemVer |

SemVer bump classification: MAJOR = invariant removed/weakened or trust boundary widened or previously specified behavior unspecified; MINOR = invariant added or trust boundary narrowed or new failure mode covered or new scenario; PATCH = typo / notation / status-block / cross-reference. Compose-ledger gains `intent_version`, `intent_version_prior`, `upstream_deps[].upstream_version`, `upstream_deps[].upstream_version_prior` fields for drift detection at the version level. Migration policy default: predictive (re-verify on expected need); eager for security-critical boundaries. *Dogfood needed:* a project that revises a boundary doc across an upstream-component version bump. *Lands in:* `skills/colosseum-intent/SKILL.md` adds the SemVer convention; `skills/colosseum-compose/SKILL.md` adds version fields to per-theorem ledger entries. External references: [references.md](./references.md) Section D.

---

## Trust ledger / CI

### CI-self-test pre-merge gate (proposed)

Any PR that adds a CI step must demonstrate the step passing at the commit that adds it. Otherwise CI gates added without local verification can ship broken because the gates only run after merge. Mostly a discipline ask, not a methodology ask. *Dogfood needed:* any project shipping CI infrastructure. *Lands in:* `skills/colosseum-compose/SKILL.md` CI sub-step gains an "added-CI-must-be-green-at-add-commit" rule.

### Commit-message vs code reconciliation pre-merge check (proposed)

Commit messages can claim things the diff does not deliver (and vice versa). Lightweight pre-merge check: parse the message for claims ("deferred", "implemented", "fixed N#"), grep the diff for the named entities, flag mismatches. Heuristic and human-reviewed; the goal is to surface drift, not gate strictly. *Dogfood needed:* any project. *Lands in:* `skills/colosseum-change/SKILL.md` change-record schema documents the field; `scripts/check_commit_message.py` reference implementation provides the heuristic.

---

## Lean spec layer

### Lake project + Mathlib (and VCV-io for crypto-touching projects) (proposed)

Stdlib-only spec files force Lean voices to translate Mathlib idioms to stdlib equivalents on every output, which both adds friction and produces less idiomatic Lean code. The methodology already commits to Mathlib + VCV-io + ArkLib via the tooling stack, so the spec layer should follow. Set up as a Lake project with `lakefile.lean` + `lean-toolchain` (pinned), Mathlib4 as a base dep, VCV-io for crypto reasoning, ArkLib for SNARK / IOR reasoning. Cost: ~5 min one-time (`lake update` git clone + `lake exe cache get` olean download); subsequent builds are cached. Verified-rcv evidence: stdlib-only setup added per-attempt friction across 3-way Lean discharge work; converting to Lake project resolved it. *Lands in:* `skills/colosseum-intent/SKILL.md` (Lean spec layer setup step); `skills/colosseum-compose/SKILL.md` ledger references the Lake project root. Reference setup: `verified-rcv/specs/lakefile.lean`.

### `lean-lsp` Mathlib hang workaround (proposed)

The `lean-lsp_lean_run_code` MCP server hangs on `import Mathlib` snippets outside a Lake project context — it tries to compile Mathlib from scratch (~30 min uncached) and then deadlocks. Dispatch scripts should not use `lean-lsp_lean_run_code` in agentic loops for spec-class Lean discharge work; instead, write the snippet to a file inside the parent Lake project and run `lake env lean <file>` directly. Upstream fix: lean-lsp MCP server should accept `--lake-project-root` or auto-detect, and fail-fast on Mathlib snippets when no Lake project is found. *Dogfood needed:* any Lean dispatch project. *Lands in:* `skills/colosseum-adversarial/SKILL.md` Step 4 troubleshooting block + upstream issue against lean-lsp MCP.

### Lean discharge voice ranking (proposed)

For multi-axiom Lean spec problems with library context (Mathlib + VCV-io), frontier general-purpose models (Claude Agent tool, single-shot gpt-5.5 direct API, Gemini, Kimi) are more reliable than Lean-specialist models (Leanstral). The opencode + lean-lsp agent loop is unreliable until the Mathlib hang above is addressed. Workflow default: Claude (Agent tool) as primary voice for Lean discharge; Leanstral or other Lean-specialist models as secondary / second-opinion (useful for ideas, not load-bearing for correctness). Single-shot frontier models via direct API as third voice. *Lands in:* `skills/colosseum-compose/SKILL.md` adds "Voice selection for Lean discharge" sub-step. This subsumes the theorem-prover-specialist exclusion (Lean-specialist models excluded from BOTH adversarial spec review AND multi-axiom proof discharge; they remain useful for single-tactic-step verification work via `mcp__goedel__propose_lean_tactic`).

---

## Validation criteria (per-improvement, for promotion to stable)

Each proposed improvement promotes from this file into a SKILL when its dogfood project produces direct evidence that exercises the pattern. The general shape:

- **System-of-intents**: bidboard run produces a multi-component intent decomposition referenced by at least one adversarial pass and one compose-ledger entry.
- **Per-section dispatch**: a run uses per-section dispatch and synthesis correctly aggregates section-local findings; at least one cross-section finding is caught by aggregation.
- **File-access subagent dispatch**: a run dispatches via OpenCode file-access subagents and the manifest records per-voice file-access traces; a subagent reads a section the inlined-prompt mode would not have included.
- **Frontier-tier requirement**: a system-level run dispatches with a documented frontier-tier panel; demonstrates a finding only frontier voices surfaced.
- **Assume-guarantee**: component intents carry assume/guarantee clauses; boundary docs record implication-links; a system-level conjunction theorem is recorded in the compose-ledger.
- **SemVer + compose-ledger versioning**: a boundary doc published with a SemVer pin against component intents; a re-verify pass correctly identifies drift using the version fields.
- **CI-self-test gate**: a CI step's introducing PR demonstrates the step green on that commit.
- **Commit-message reconciliation check**: a PR with a mismatch between message and diff is caught by the heuristic.
- **Lake project + Mathlib default**: a crypto-touching project's Lean spec layer is set up as a Lake project with Mathlib + VCV-io from the start; the ledger entry references the Lake root.
- **lean-lsp Mathlib hang**: a Lean dispatch project uses `lake env lean <file>` (or a fixed lean-lsp MCP) without the agent loop hanging.
- **Lean discharge voice ranking**: a Lean discharge run uses the documented voice ranking and produces clean proofs.
- **Field-spec discipline**: an intent's field-spec table catches an underspecified binary-data field before it ships.

Until promoted, dogfood projects MAY adopt the pattern locally; the methodology does not yet require it.

---

## Open architecture question — executable form of compose / change / adversarial checks

Several shipped improvements have a "documented form" that is the prose discipline, plus an "enforced form" (a programmatic check at the relevant step) that is gated on a Colosseum architectural decision: does compose / change / adversarial run a programmatic check at the relevant step, or stay prose-only? The decision shape: prose-only is cheaper to maintain and easier to teach; programmatic is more reliable but harder to keep stable across tool drift. The decision remains open across improvement waves.
