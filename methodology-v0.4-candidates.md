# Methodology v0.4 candidates — tentative asks awaiting dogfood validation

**Audience**: colosseum maintainers / colosseum agent.
**Origin**: pattern survey conducted during verified-rcv Round 3a dogfood (external literature + methodology-internal reasoning); plus open items carried forward from v0.2 (Quartz Round A) and v0.3 (Round 3a) that remain gated on a future architectural decision.
**Status**: drafted 2026-05-15; updated as v0.4 dogfood projects produce evidence to promote or retire each candidate.

## Discipline — stable vs tentative

The v0.3 ask set split into two parts:

- **Stable** (Asks A–H): backed by direct Round 3a evidence. Back-ported into SKILLs / docs as v0.3 ships. See [where v0.3 stable asks landed](#where-v03-stable-asks-landed) below.
- **Tentative** (Asks I–N): backed by pattern survey only — no Colosseum dogfood has exercised the pattern in anger. Documented here with the recommended dogfood project. Codified into SKILLs only after v0.4 dogfood validates.

This file is the live list of the tentative half. As each candidate validates, its content migrates into the relevant SKILL.md and the entry here is replaced with a one-line pointer (the same shape as the table below for the stable set).

## Where v0.3 stable asks landed

For audit / traceability. Full provenance is preserved in the verified-rcv `.colosseum/` artifacts and in [references.md](./references.md).

| Ask | Topic | Lands in |
|---|---|---|
| A | Gateway provider as first-class channel | `mcp/external-model-mcp/` v0.2 (code + README); `skills/colosseum-adversarial/SKILL.md` Step 4 dispatch table |
| B | Per-route timeout caveats published as operational guidance | `skills/colosseum-adversarial/SKILL.md` Step 4 timeout-caveats block; `verified-rcv/.colosseum/gateway-bugs-2026-05-14.md` (operator reference) |
| C | Theorem-prover specialist exclusion from spec adversarial | `skills/colosseum-adversarial/SKILL.md` Step 4 "Excluded model classes" paragraph |
| D | Cross-session LM Studio contention discipline | `skills/colosseum-adversarial/SKILL.md` Step 4 ops-notes block; reference impl `verified-rcv/.colosseum/scripts/fan_out_dispatch.py` |
| E | Manifest-protocol dispatch (`colosseum_run.py`) | `scripts/colosseum_run.py` + `scripts/README.md`; SKILL.md Step 4 forward-pointer |
| F | Voice-failure-mode catalog as synthesis obligation | `skills/colosseum-adversarial/SKILL.md` Step 6 three-section synthesis |
| G | Overlap-matrix + theme-clustering synthesis format | `skills/colosseum-adversarial/SKILL.md` Step 6 prescribed format |
| H | Voice diversity metadata (family + lineage + inference-seat) | `skills/colosseum-adversarial/SKILL.md` Step 5; `scripts/colosseum_run.py` manifest schema |

---

## Tentative candidates (v0.4 targets)

Each candidate names its recommended dogfood project — the first multi-component project to validate the pattern in anger.

### Ask I — System-of-intents shape (multi-component intent decomposition)

**Pattern source**: synthesis of TLA+ EXTENDS/INSTANCE, DDD bounded contexts + context maps, seL4 abstract specification layering, CompCert phased compilation, ADRs. Full citations in [references.md](./references.md) Section A.

**Symptom this addresses**: Round 3a's verified-rcv intent at ~25K tokens already pushes (a) the Claude Code Read tool's 25K limit, (b) reasoning-model output budgets when concatenated for synthesis, (c) gateway timeout caps for adversarial dispatch at long prompts. For systems with 3+ components, a single monolithic intent doc is infeasible.

**Proposed shape**:

```
<system-repo>/
├── intent.md                          # SYSTEM intent (top-level claim, cross-component invariants, system trust boundaries)
├── components/
│   ├── <component-a>/.colosseum/intent.md    # component intent (its own Sections 1-8)
│   └── ...
├── boundaries/
│   ├── <component-a>--<component-b>.md       # per-pairwise-boundary doc
│   └── ...
├── decisions/
│   ├── ADR-001-...md                          # cross-cutting decisions, status-tracked
│   └── ...
└── .colosseum/
    └── compose-ledger.md
```

The five DDD relationship patterns (Customer/Supplier, Open Host Service, Published Language, Anti-Corruption Layer, Shared Kernel) are the taxonomy for boundary doc relationship classification.

**Recommended dogfood**: bidboard (anti-sniping auction contract + auction logic + frontend) — the next planned dogfood at the time of this writing. It has at least 3 components and one cross-project boundary (to a chain or a contract-on-chain).

**Codified form (v0.4 target)**: extend `skills/colosseum-intent/SKILL.md` with the system-of-intents decision tree; new skill `colosseum-boundary` for boundary doc elicitation; `skills/colosseum-compose/SKILL.md` extended to track per-theorem intent-doc provenance.

**Open question**: when should a project split? Pre-emptive split risks premature decomposition; reactive split risks doing it under pain. Suggestion: monolithic intent stays viable to ~25K tokens; system-of-intents kicks in at the 3rd component, regardless of token count. Validate against bidboard.

### Ask J — Per-section adversarial dispatch (scaling escape hatch)

**Pattern source**: Chroma "Context Rot" research ([Context Rot — Chroma](https://research.trychroma.com/context-rot)) + ∞Bench / LoCoBench / BABILong benchmarks. Empirical finding: model reliability degrades non-monotonically as input length grows; per-section dispatch keeps each call in the reliable context range. Full citations in [references.md](./references.md) Section C.

**Symptom this addresses**: Round 3a observed reasoning-budget burnout at 32K reasoning tokens (gemma) and content-truncation at 8K output tokens (kimi). Per-section dispatch sidesteps both: each voice attacks one section with cross-section context as appendix; synthesis aggregates.

**Proposed shape**: SKILL.md Step 4 documents an alternative dispatch mode where each voice receives `(system_prompt, target_section, cross_section_summary, brief)` instead of `(system_prompt, full_intent, brief)`. Cost: N×M calls instead of N. Benefit: each call fits cleanly in budget; voice attention is not diluted across N sections.

**Recommended dogfood**: any v0.4 project with intent > 50K tokens (likely bidboard if it grows beyond verified-rcv's size).

**Codified form (v0.4 target)**: extend `skills/colosseum-adversarial/SKILL.md` Step 4 with per-section dispatch as a named alternative; `scripts/colosseum_run.py` adds a `init --per-section` mode that creates one manifest entry per (voice × section) pair.

### Ask K — File-access subagent dispatch (the OpenCode pattern)

**Pattern source**: OpenCode's native subagent architecture with `permission.read: allow` ([OpenCode Agent System docs](https://opencode.ai/docs/agents/)). Subagent reads what it needs on demand rather than receiving an inlined prompt.

**Symptom this addresses**: the inlined-everything dispatch pattern (current default) forces every voice to ingest the entire intent doc each time, even if it only needs to examine one section. Context cost is high; context rot risk is high. File-access subagents read just-in-time and bound their own attention.

**Proposed shape**: SKILL.md Step 4 documents file-access subagent dispatch as the recommended shape for any system whose intent exceeds 25K tokens or for adversarial reviews of boundary docs (which require reading both component intents the boundary references).

**Recommended dogfood**: any v0.4 project run via OpenCode + Claude Code dual-harness using the `colosseum_run.py` manifest protocol.

**Codified form (v0.4 target)**: extend `skills/colosseum-adversarial/SKILL.md` Step 4 with explicit guidance on when to choose file-access subagents over inline-prompt dispatch. The current SKILL.md already mentions OpenCode in the harness-agnostic-manifest section (v0.3 Ask E); this candidate makes the file-access discipline explicit.

### Ask L — Frontier-tier dispatch requirement at scale

**Pattern source**: ∞Bench / LoCoBench / BABILong benchmark literature ([references.md](./references.md) Section C). Empirical finding: frontier-tier models (Claude 4.x, Gemini 2.x/3.x, GPT-5.x, Kimi-k2.6, GLM-4.7) substantially outperform mid-tier on multi-document reasoning tasks; the gap widens as context length grows.

**Symptom this addresses**: for system-of-intents adversarial review at >100K effective context, mid-tier voices (mistral-119b, gemma-26b under 50K — both excellent in Round 3a's ~25K range) are *complementary* but *not sufficient* in isolation. The methodology must be explicit about this.

**Proposed shape**: SKILL.md Step 4 documents a "frontier-tier requirement" for system-level adversarial review. Mid-tier voices remain valuable for component-level review; the system-level review requires at least 3 frontier voices.

**Recommended dogfood**: any v0.4 system-of-intents project. The frontier-tier requirement is calibrated against effective context size, not project complexity directly.

**Codified form (v0.4 target)**: SKILL.md Step 4 names "frontier tier" explicitly with a model-id list (refreshed per major Colosseum release).

### Ask M — Inter-component invariants via assume-guarantee reasoning

**Pattern source**: [Dardik & Kang 2025 — Compositional Inductive Invariant Inference via Assume-Guarantee Reasoning](https://arxiv.org/abs/2509.06250), [Liang/Feng POPL 2012 RGSim](https://hongjin-liang.github.io/papers/popl12-rgsim.pdf), [CSim² TOPLAS 2021](https://dl.acm.org/doi/fullHtml/10.1145/3436808). Full citations in [references.md](./references.md) Section B.

**Symptom this addresses**: the concern that pairwise specs grow exponentially with component count. Established assume-guarantee theory shows the cost is O(n) component contracts + O(boundaries) handshake invariants + 1 conjunction theorem — linear, not exponential.

**Proposed shape**: each component intent's Section 3 (Invariants) is augmented with an explicit *assume* clause (what the component requires of its environment) + *guarantee* clause (what it provides). The boundary doc records the implication-link: A.guarantee → B.assume. The compose-ledger records the system-level conjunction theorem.

For N-ary interactions (3+ components participating in a single invariant), escalate to a BIP-style n-ary interaction doc following [Sifakis Verimag 2010](https://www-verimag.imag.fr/~sifakis/RecentPublications/2010/iet-sen.pdf).

**Recommended dogfood**: bidboard (3 components, at least 2 inter-component invariants — anti-sniping check + auction-result-equals-bid-set).

**Codified form (v0.4 target)**: `skills/colosseum-intent/SKILL.md` adds the assume/guarantee structure to Section 3 invariants when in system-of-intents shape; new skill `colosseum-boundary` walks the user through an A.guarantee → B.assume implication-link.

### Ask N — Intent doc + boundary doc + spec versioning (SemVer + compose-ledger version fields)

**Pattern source**: [SemVer spec](https://zuplo.com/learning-center/semantic-api-versioning), [Lam 2020 — Putting Semantics into Semantic Versioning](https://arxiv.org/pdf/2008.07069), [Consumer-Driven Contracts](https://github.com/lirantal/enterprise-applications-patterns/blob/master/backend/consumer-driven-contracts.md), [Brahmia 2024 schema versioning literature review](https://www.worldscientific.com/doi/10.1142/S2972370124300024). Full citations in [references.md](./references.md) Section D.

**Symptom this addresses**: even without inter-component drift, single-component intent revisions need versioned identification for: audit trail; cross-reference stability (boundary docs reference component intents at specific versions); compose-ledger drift detection; debugging "which intent was this proof built against?"

**Proposed scheme**:

| Artifact | Versioning |
|---|---|
| Intent doc | SemVer (MAJOR.MINOR.PATCH) |
| Boundary doc | SemVer + component-version pins (`compatible_with: { component-a: '>=0.3.0, <0.4.0' }`) |
| Formal spec (Quint / Lean) | SemVer; MAJOR bumps require refinement-theorem witness OR explicit breakage notice |
| ADRs | status-flag (proposed / accepted / superseded), no SemVer |

**SemVer bump classification**:
- MAJOR: invariant removed; invariant weakened (new implies old, not vice versa); trust boundary widened; previously specified behavior becomes unspecified
- MINOR: invariant added; trust boundary narrowed; failure mode covered explicitly; new scenario walkthrough
- PATCH: typo, notation cleanup, status-block update, cross-reference fix, worked-example arithmetic clarification (correct answer preserved)

**Compose-ledger integration**: per-theorem entry gains `intent_doc`, `intent_version`, `intent_version_prior`, `upstream_deps[].upstream_version`, `upstream_deps[].upstream_version_prior` fields. Enables drift detection at the version level (not just bundle-cardinality level).

**Migration policy default**: predictive (re-verify on expected need); eager (re-verify immediately) for security-critical boundaries. Boundary doc declares its migration policy explicitly.

**Recommended dogfood**: verified-rcv (already retroactively version-numbered: v0.1.0 first draft → v0.2.0 first-pass-adversarial revision → v0.2.1 sanity-pass → v0.3.0 re-adversarial revision — see the header of `verified-rcv/.colosseum/intent.md`). The revision-log section captures the bump rationale; next dogfood validates the boundary-doc + compose-ledger integration.

**Codified form (v0.4 target)**: `skills/colosseum-intent/SKILL.md` adds the SemVer convention; `skills/colosseum-compose/SKILL.md` adds version fields to per-theorem ledger entries; `scripts/colosseum_run.py` manifest records the intent-doc version under review.

---

## Round 3a continuation candidates (validated 2026-05-19)

A second wave of Round 3a fan-out cycles (v10 fresh-state, v11 intent-tightened, cross-critique, defense, re-cross-critique) produced direct evidence for the next six asks. Unlike Asks I–N (pattern-survey-only), these have dogfood backing — but have not yet been back-ported into SKILLs. They are tentative in that sense only.

Evidence trail: `verified-rcv/.colosseum/specs/{synthesis-2026-05-19, cross-critique-2026-05-19, critique-and-defense-2026-05-19, critique-revised-canonical-2026-05-19}/`.

### Ask O — Cross-critique as standard post-fan-out step

**Evidence**: 2026-05-19 cross-critique round caught two defects that v11 synthesis alone missed — kimi flagged gpt-5.5's tautological S9 shadow (`val s9_shadow = true`); gpt-5.5 flagged kimi's B8 tautology. Both critics also independently identified the canonical's S8/S9 trivial encoding in a separate canonical-critique round. Synthesis aggregation across voices did NOT detect tautological-shadow defects because each voice fell into the same trap. Cross-voice review broke the symmetry.

**Symptom this addresses**: Tautological-shadow defects (`val foo_shadow = true`, vacuous bounds in place of real predicates) typecheck cleanly, satisfy all_invariants vacuously, and survive intent-tightened fan-out + synthesis. They surface only when a voice is asked to read another voice's spec with explicit failure-mode prompts.

**Proposed shape**: After fan-out + synthesis, dispatch a cross-critique round. Each voice reviews ANOTHER voice's spec (not their own) against a Q1/Q2/Q3 structured prompt:
- Q1: Does each named predicate encode the intent's claim, or is it tautological/vacuous?
- Q2: Are there state-space gaps where the spec is unreachable in regions the intent requires reachable?
- Q3: Single most material remaining concern?

The Q1/Q2/Q3 shape forces structured findings instead of free-form review, which suppresses sycophancy and produces non-trivial findings even when the spec is broadly sound.

**Recommended dogfood**: any v0.4 multi-voice project where synthesis produces a candidate canonical.

**Codified form (v0.4 target)**: extend `skills/colosseum-adversarial/SKILL.md` with a new Step 6.5 (cross-critique) between Step 6 (synthesis) and acceptance. `scripts/colosseum_run.py` manifest gains a `cross_critique` phase with each entry naming reviewer voice + target voice + structured prompt.

### Ask P — Defense round for canonical-defect adjudication

**Evidence**: 2026-05-19 critique-and-defense round on the verified-rcv canonical. After two reviewers (kimi, gpt-5.5) independently flagged the S8/S9 omission, two defense voices were dispatched at `--variant high` with the explicit defend/concede/third-option protocol. Both defenses CONCEDED with reasoning ("the predicates as stated are bounds, not the intent's claim"). No anchoring observed. The protocol produced actionable consensus, not a stalemate.

**Symptom this addresses**: A naive synthesis step may anchor on a flawed canonical that nobody questions in a free-form review. Defense round forces structured choice — defend (with reasoning), concede (with reasoning), or third-option (with new proposal) — making the protocol's failure mode explicit and surfacing genuine disputes when they exist.

**Proposed shape**: When cross-critique surfaces a non-trivial defect claim, dispatch a defense round before applying fixes. Voices: ideally the canonical's author voice + one of the original critics + a third independent voice. Each voice must explicitly defend / concede / propose-third-option with reasoning. Near-unanimous concede mandates the fix.

**Recommended dogfood**: any v0.4 project where cross-critique flags a load-bearing defect in the canonical.

**Codified form (v0.4 target)**: extend `skills/colosseum-adversarial/SKILL.md` Step 6.5 / 6.6 with the defense protocol. Reference dispatch: `verified-rcv/.colosseum/scripts/critique_and_defense_dispatch.py`.

### Ask Q — Intent-tightening on encoding-discipline as the convergence lever

**Evidence**: 2026-05-19 v10 (fresh-state regeneration on intent v0.3.1) did NOT converge voices on the same encoding axes that diverged in v9 — confirming fresh-state alone is not a convergence lever. v11 with intent v0.3.2 added two encoding-discipline notes — A2 (enclave-layer state requirement for B10 chain-side projection) and A3 (B2 snapshot-invariant requirement, not pure action-guard) — and DID move voice convergence on those exact axes. Intent-tightening on encoding-discipline is the convergence lever; re-rolling the dice on the same intent is not.

**Symptom this addresses**: When fan-out voices diverge on the same encoding choice across regenerations, the divergence is not stochastic — it reflects under-specification in the intent. Re-running the fan-out without changing the intent reproduces the divergence. The intent doc must be revised to constrain the encoding choice.

**Proposed shape**: Intent doc carries an "encoding-discipline notes" section (A1, A2, A3, ...) for each axis where fan-out has surfaced divergence-as-under-specification. Each note specifies WHAT MUST be in the spec (e.g., A2: "the protocol model MUST include enclave-side state variables for B10 chain-side projection to be checkable"). The next fan-out converges on that axis.

**Recommended dogfood**: any v0.4 project where two fan-out runs show divergence on the same encoding choice.

**Codified form (v0.4 target)**: `skills/colosseum-intent/SKILL.md` adds an "encoding-discipline notes" subsection pattern (Section 9 of the intent template, or appendix). `colosseum-adversarial/SKILL.md` Step 6 synthesis explicitly searches for divergence-as-symptom-of-under-specification and proposes encoding-discipline-note candidates back to the intent.

### Ask R — Re-cross-critique after canonical revision (mandatory if revision touches load-bearing predicates)

**Evidence**: 2026-05-19 re-cross-critique caught two defects introduced by the canonical revision itself — kimi flagged the `bt_tallied = oneOf(Set(0,1,2,3,5))` coverage hole (missing 4 for 5-candidate case, making resolution unreachable from any 4-voter trace); gpt-5.5 flagged `is_tally_spec_output`'s name overstating its scope (chain-observable subset only, not full IRV correctness). Both findings actionable; both fixes applied same session. Without the re-cross-critique step, both regressions would have shipped silently.

**Symptom this addresses**: Fixes to verified specs introduce new defects, especially when the fix shape is novel (bounded nondet, scope-rename, new ghost variable). The canonical author's local context is insufficient to catch all regressions. External eyes, re-applying the same Q1/Q2/Q3 protocol, are cheap (~5 min wall-clock per voice) and reliably catch revision-induced defects.

**Proposed shape**: After applying fixes from cross-critique + defense, run a re-cross-critique round before accepting the revision. Same harness as the original cross-critique; same Q1/Q2/Q3 prompt structure with "is the fix structurally sound?" prepended. Q2 narrowed to "did the revision introduce new defects?"

**Recommended dogfood**: any v0.4 project where canonical is revised in response to cross-critique findings touching load-bearing predicates.

**Codified form (v0.4 target)**: extend `skills/colosseum-adversarial/SKILL.md` Step 6.7 with mandatory re-cross-critique whenever a revision touches a load-bearing predicate or invariant. Reference dispatch: `verified-rcv/.colosseum/scripts/revised_canonical_critique.py`.

### Ask S — Ghost-variable encoding for action-guard-only invariants

**Evidence**: kimi's 2026-05-19 re-cross-critique flagged B1 (tally_result monotone-once-set) as encoded only as `publish_result`'s action-guard `not(contract_tally_result.present)`. No state-side invariant catches an action-set drift that bypasses the guard. By contrast B2 in v0.3.2 was correctly encoded as a snapshot ghost variable (`ghost_ballots_at_end_at`) plus a state invariant (`inv_b2_ballots_at_end_at_frozen`). The pattern generalizes to B5/B6/B7 (all currently action-guard-only in verified-rcv's canonical).

**Symptom this addresses**: When a behavioral invariant is encoded only as an action-guard, the model checker has nothing to flag if a future action is added or modified that bypasses the guard. Action-set drift becomes a silent correctness regression. The model checker's job is to check invariants; encoding the property as a guard alone takes the model checker out of the verification loop for that property.

**Proposed shape**: When a behavioral invariant could be encoded as either action-guard OR ghost-variable+state-predicate, prefer the latter. Pattern:
- Ghost variable captures the load-bearing state at the moment of the protected transition (e.g., `ghost_published_tally` snapshots `contract_tally_result` at publication).
- State invariant checks the relation against the ghost (e.g., `if (contract_tally_result.present) then contract_tally_result == ghost_published_tally`).
- Action-guard remains for liveness/well-definedness but is no longer load-bearing for safety.

**Recommended dogfood**: any v0.4 protocol spec with monotone-set / freeze-at-time / write-once invariants. Verified-rcv's B1/B5/B6/B7 are direct back-port targets.

**Codified form (v0.4 target)**: extend or create `skills/colosseum-spec-encoding/SKILL.md` (or section in `colosseum-adversarial/SKILL.md` Step 5) naming ghost-variable+state-invariant as the preferred encoding pattern for the freeze-at-time invariant class. Document the action-set-drift failure mode the pattern defends against.

### Ask T — `--variant high` (or equivalent reasoning-effort flag) as default for spec-class adversarial work

**Evidence**: 2026-05-19 cross-critique, defense, and re-cross-critique rounds all dispatched at `--variant high`. Findings produced were non-trivial (tautological-shadow detection, scope-name overstating, state-space coverage hole) and the defense rounds produced honest concessions rather than sycophantic agreement. The CLI flag is accepted by both gateway-routed and native-provider channels in opencode; the `opencode.jsonc` `variants.high.reasoningEffort` config supports it across the reasoning-tier models (claude-opus-4-7, gemini-2.5-flash, nemotron, gpt-5.5, kimi-k2-6).

**Symptom this addresses**: Reasoning models at default reasoning-effort produce shallower critiques. Tautological-shadow detection in particular benefits from the additional reasoning budget — the failure mode is "predicate typechecks and reads as substantive but does no work," which requires the reviewer to actually evaluate what the predicate says, not just that it parses.

**Proposed shape**: Spec-class adversarial dispatch (intent review, spec review, cross-critique, defense, re-cross-critique) defaults to `--variant high` (or provider-specific equivalent) for any model with `reasoningEffort` configuration. Cost: more tokens per call. Benefit: adversarial quality, which is the load-bearing axis for adversarial passes.

**Recommended dogfood**: any v0.4 project. Already exercised in verified-rcv Round 3a continuation; cost was acceptable and findings improved.

**Codified form (v0.4 target)**: extend `skills/colosseum-adversarial/SKILL.md` Step 4 dispatch table with `--variant high` annotation per voice (or provider-equivalent reasoning-effort flag). `scripts/colosseum_run.py` manifest schema gains a `variant` field per-voice with default `high` for spec-class phases. Document provider-specific equivalents (e.g., Anthropic `thinking.budget_tokens`, OpenAI `reasoning.effort`, Google `thinking.thinking_budget`, NVIDIA `extra_body.reasoning_effort`).

### Ask U — Lean spec layer defaults to a Lake project + Mathlib (and VCV-io for crypto-touching projects)

**Evidence**: 2026-05-23 Round 3a discharge continuation. The Lean math spec at `verified-rcv/specs/RcvSpec.lean` was initially set up as a single standalone file (no Lake project), stdlib-only. This was inconsistent with the methodology's own tooling stack (the README §Related work and §Tooling stack both name VCV-io + ArkLib + Mathlib as foundations for crypto-touching projects). The cost of stdlib-only was real: Leanstral and other Lean-trained models default to Mathlib idioms (`linarith`, `induction'`, `Disjoint`), so per-attempt friction compounded across the 3-way comparison and discharge work. Converting `specs/` to a Lake project with Mathlib + VCV-io took ~5 min one-time (mostly `lake update` git clone + `lake exe cache get` olean download); subsequent builds are cached and fast.

**Symptom this addresses**: stdlib-only spec files force Lean voices to translate Mathlib idioms to stdlib equivalents on every output, which both adds friction and produces less idiomatic Lean code. The methodology already commits to Mathlib + VCV-io + ArkLib via the tooling stack, so the spec layer should follow.

**Proposed shape**:

- **`skills/colosseum-intent/SKILL.md`** (when the project is crypto-touching or otherwise likely to benefit from Mathlib): add a step recommending the Lean math spec live in a Lake project with `lakefile.lean` + `lean-toolchain` (pinned), Mathlib4 as a base dep, VCV-io for crypto reasoning, ArkLib for SNARK / IOR reasoning.
- **`skills/colosseum-compose/SKILL.md`**: document the Lake-project shape in the integration-ledger template; the ledger's per-tool-coverage row for Lean should reference the Lake project root, not a single file.
- **Reference setup**: the `verified-rcv/specs/lakefile.lean` is a working minimal example pinned to Lean 4.29.0 + Mathlib4 v4.29.0 + VCV-io v4.29.0.

**Recommended dogfood**: bidboard or any other v0.4 crypto-touching project. Validate by attempting Lean proof discharge against the Lake-project spec layer.

**Codified form (v0.4 target)**: `colosseum-intent` SKILL gains a "Lean spec layer setup" sub-step. `colosseum-compose` SKILL's ledger template references the Lake project root. The `methodology-v0.4-candidates.md` validation criteria gain a row for Ask U.

### Ask V — `lean-lsp_lean_run_code` MCP call hangs on `import Mathlib` snippets outside Lake project context

**Evidence**: 2026-05-23 attempt at 3-way Lean discharge comparison. Dispatching gpt-5.5 via opencode + the project-local `lean-spec-generator` agent, the agent invoked `lean-lsp_lean_run_code` on a Lean snippet starting with `import Mathlib`. The MCP server hung indefinitely (80+ minutes wall-clock, ~17s CPU time at the opencode wrapper). Likely cause: the lean-lsp MCP runs Lean in a scratch context that doesn't inherit the parent Lake project's pre-built Mathlib oleans, so it tries to compile Mathlib from scratch (~30 min uncached) and then deadlocks at some point (memory exhaustion, LSP heartbeat lost, etc.). The opencode agent's MCP client has no timeout configured and waits forever.

**Symptom this addresses**: Lean-spec-class adversarial work via opencode + `lean-lsp_lean_run_code` is unreliable when Mathlib is needed (which is the recommended setup per Ask U). Multi-voice fan-out can stall indefinitely, blocking dispatch progress.

**Proposed shape** (two-part fix):

1. **lean-lsp MCP server** should accept a `--lake-project-root` arg (or auto-detect via `lakefile.lean` walk-up) and route `lean_run_code` invocations through that project's environment. If no Lake project is found and the snippet contains `import Mathlib`, fail-fast with a clear error rather than attempting a from-scratch Mathlib compile.
2. **Dispatch scripts** should not use `lean-lsp_lean_run_code` in agentic loops for spec-class Lean discharge work until #1 lands. Instead, write the snippet to a file inside the parent Lake project and run `lake env lean <file>` directly (single-shot, no MCP round-trip).

**Recommended dogfood**: any v0.4 Lean dispatch project. Validate that the lean-lsp MCP fix unblocks `opencode run --agent lean-spec-generator --model openai/gpt-5.5 --variant high` from hanging on Mathlib-bearing snippets.

**Codified form (v0.4 target)**: file an issue on the lean-lsp MCP server repo with the reproducer (snippet + observed hang). Document the workaround (use `lake env lean` directly) in `skills/colosseum-adversarial/SKILL.md` Step 4 troubleshooting block alongside the gateway-bugs notes.

### Ask W — Voice ranking for Lean proof discharge (Claude > Leanstral > opencode-gpt-5.5 in current state)

**Evidence**: 2026-05-23 3-way comparison on `verified-rcv/specs/RcvSpec.lean`'s `s7_voter_partition`. All three voices were given the same prompt (diagnose missing axiom + propose fix + write proof).

- **Claude (Agent tool, general-purpose subagent)**: consistently cleanest output. Minimal axiom with `cs.Nodup` premise. Clean 3-line proof. Identified `h_nodup` as required by the axiom but not the proof body (subtle correctness point). Polished alternative `List.Perm`-based version offered.
- **Leanstral (local LM Studio, `leanstral-2603-mlx`)**: structurally-right ideas but multiple Lean compile bugs (missing `pk` argument on the proposed axiom, used unknown `List.map_length` (vs stdlib `List.length_map`), tried to unfold opaque `IRV_spec` via simp). Self-correction with explicit error feedback regressed rather than improved — fixed the wrong function in the second attempt.
- **gpt-5.5 (opencode + lean-lsp-iterated)**: structurally equivalent to Claude's. Eventually produced a clean solution. But the opencode + lean-lsp agent loop hung for 80+ min on the `import Mathlib` snippet (see Ask V). The salvaged solution (extracted from the LSP run code mid-hang) compiled cleanly.

Single-shot gpt-5.5 via direct API (not opencode + lean-lsp) was not exercised due to MCP credential setup; expected to work and would likely match Claude's quality.

**Symptom this addresses**: Lean-specialist models (Leanstral) are not currently reliable for multi-axiom spec problems even with library context (Mathlib + VCV-io available). Frontier general-purpose models (Claude, gpt-5.5) are more reliable in this regime. Workflow defaults need to reflect this.

**Proposed shape**:

- **`skills/colosseum-compose/SKILL.md`**: Lean discharge sub-step defaults to Claude (Agent tool) as primary voice. Leanstral (or other Lean-specialist models) is a secondary / second-opinion voice — useful for ideas, not load-bearing for correctness.
- **Single-shot frontier models** (gpt-5.5 direct API, Gemini, Kimi) are acceptable third voices when Claude is unavailable; opencode + lean-lsp agent-loop dispatch is unreliable until Ask V is addressed.

**Recommended dogfood**: bidboard or any v0.4 Lean discharge project. Validate that the workflow defaults produce clean Lean proofs without the per-attempt friction observed with Leanstral on multi-axiom spec problems.

**Codified form (v0.4 target)**: `colosseum-compose` SKILL gains a "Voice selection for Lean discharge" sub-step naming the recommended order. v0.3 Ask C's "theorem-prover specialist exclusion from spec adversarial" is partly subsumed here: Lean-specialist models are excluded from BOTH adversarial review (Ask C) AND multi-axiom proof discharge (Ask W); they remain useful for single-tactic-step verification work (the original `goedel-mcp` `propose_lean_tactic` use case).

---

### Ask AB — code-adversarial as a first-class stage with six named lenses

**Evidence**: verified-rcv 4-round audit retrospective (2026-05-26, `verified-rcv/.colosseum/methodology-retrospective-2026-05-26.md`). Across 4 audit rounds (intent v0.3.7 to v0.3.12), 13 high-severity findings closed. Of those 13, 8 would have been caught by an internal code-adversarial stage with six named lenses applied to the implementation against the intent. The audit rounds themselves were the de-facto code-adversarial; this ask internalizes that stage so the catch happens before external audit. Without this stage, multi-round cascades occurred: C2 took R1+R2; C3 took R1+R2+R4.

**Symptom this addresses**: Colosseum v0.2 had intent-elicitation, intent-adversarial, Quint-spec, Lean-spec, Aeneas-extraction, code-implementation, Kani-harness stages, but no stage that reads the implementation against the intent's clauses. The result: bugs of the shape "intent says X must hold; code does not enforce X" went uncaught.

**Proposed shape**: After code-implementation produces a commit and before audit, an internal red-team agent (distinct from the code-implementation author) applies the six lenses below to the implementation, referencing intent and ledger:

- **AB.1 commitment-coverage**: For every hash, signature payload, ReportData, or serialized commitment in contract or runtime, enumerate the attacker-controllable degrees of freedom (DoFs). Confirm each DoF is bound in the commitment's coverage set. Deliverable table: `(commitment, attacker DoFs, bound by, gap)`. Catches the replay-narrow-binding cluster (verified-rcv M2 election_id, N4 chain_id, N22 registration, B6 ballots_hash, minor m7 ECIES chain context).
- **AB.2 clause-to-line discharge**: For every named intent clause (B-clauses in intent §3.2, ledger links in §8.7, trust assumptions in §6.x), point at a code-line citation (file:line) that discharges it. Deliverable: `(clause, expected discharge, actual code line, status in {discharged, partial, gap})`. Catches the trust-assumption-decomposition cluster (verified-rcv C2 envelope-only, C3 enclave_pubkey provenance, N1 gnark verification deferred).
- **AB.3 deferred-is-panic**: For every branch labeled deferred/stub/mock/TODO in the production build (default features), confirm the branch panics. Catches stub-as-Ok pattern (verified-rcv C1 Mock variant accepted, N11 real-zkdcap returns Err stub).
- **AB.4 who-controls**: For every field of stored state, name the supplier and the validation. Deliverable: `(field, supplier, validation, gap)`. Catches admin-input cluster (verified-rcv N2 admin picks pubkey, M1 partial, M3 partial).
- **AB.5 API field-name fidelity**: For every JSON, proto, or borsh field in a public API surface, confirm the value placed at the field carries the semantic the field name implies. Catches API-presentation-drift (verified-rcv M5 mrtd_hex slot held compose_hash).
- **AB.6 deferral-justification audit**: For every deferred finding from a prior audit round, decompose the deferral justification into refutable claims and audit each. Catches wrong-deferral events (verified-rcv N13 to N22, where R3's "N2 timelock makes this acceptable" was wrong since N2 prevents registry rotation not registration-quote replay).

Deliverable file: `.colosseum/code-adversarial/<date>.md` with the six tables and the list of findings.

**Recommended dogfood**: any v0.4 project after the implementation layer lands and before external audit. The stage operator MUST be a different agent than the code-implementation author (otherwise drift toward author-self-review).

**Codified form (v0.4 target)**: **SHIPPED**: see `skills/colosseum-code-adversarial/SKILL.md`.

### Ask AC — Top-down Kani harness catalog derived from §8.7 trust-chain ledger

**Evidence**: verified-rcv methodology retrospective showed Kani had 10 harnesses, all targeting IRV result structure (B1, S4, S6, S7, S8, S9, S10, already-voted, already-resolved, derive_phase). Zero harnesses targeted attestation verification, registry shape, gnark public_inputs construction, canonical_serialization byte layout, or ECIES decoder rejection paths. The catalog was built bottom-up from theorem inventory; the trust-boundary surfaces (where 6 of 13 high-severity findings lived) were uncovered.

**Symptom this addresses**: Kani-harness-catalog construction without an explicit derivation source produces a catalog that mirrors the prover's mental model rather than the trust-boundary surface. M4 (declaration-order discipline) would have been caught by Kani in seconds, but no harness was written.

**Proposed shape**: Every link in intent §8.7 (the trust-chain ledger) must have either (a) a Kani harness named `<link_id>_<assertion>` that exercises the link's claim, or (b) an explicit annotation `kani: skipped because <reason>` with a closed-list reason (e.g., "off-chain", "covered by cross-layer-ledger byte-equality test", "Verus-only", "axiom"). CI verification feature runs all harnesses; a missing harness without skipped-annotation fails CI.

**Recommended dogfood**: any v0.4 project that has both a §8.7-style trust-chain ledger and a Kani-eligible substrate (Rust contract, executable runtime code).

**Codified form (v0.4 target)**: **SHIPPED**: see `skills/colosseum-compose/SKILL.md` Step 4.4 (Kani harness catalog — derive top-down from the trust-chain ledger).

### Ask AD — Ledger-as-gate (code-line citations on every trust-chain link)

**Evidence**: verified-rcv intent §8.7 had 9 trust-chain links carefully named pre-audit. Audit finding N1 surfaced: §8.7 link 5 said "chain verifies proof," but the contract code only checked envelope shape. The ledger was a map of obligations, not a gate.

**Symptom this addresses**: ledger entries can name the right structure and still drift from code because nothing forces reconciliation between ledger claims and executable code.

**Proposed shape**: every link in §8.7 carries a `code: file:line` annotation pointing at the line that discharges the claim. For off-chain claims, the citation points to a testing harness, an external verifier, or an explicit `axiom: <reason>` annotation. CI runs a check: every §8.7 link has a citation, and every citation resolves to a non-empty line in the live codebase.

**Recommended dogfood**: any v0.4 project that has a multi-layer trust chain (contract + enclave + chain or contract + zk-verifier or similar).

**Codified form (v0.4 target)**: **SHIPPED**: see `skills/colosseum-compose/SKILL.md` Step 3 dependency-entry template (adds `code:` annotation) + Step 5.5 (CI gate — ledger-as-gate enforcement).

### Ask AE — Lifecycle-adversary stage for multi-tx admin features

**Evidence**: verified-rcv N17 (Major) was a brand-new attack class introduced by v0.3.10's registry-rotation timelock feature. The Quint model was not extended when ProposeRegistryUpdate, FinalizeRegistryUpdate, and CancelRegistryUpdate landed. No methodology stage red-teamed multi-block admin sequences combining the new transitions with existing election-lifecycle transitions. The auditor found a sequence `[CreateElection, ProposeRegistryUpdate, ..., FinalizeRegistryUpdate]` reaching a DoS state.

**Symptom this addresses**: when a contract gains a feature with multiple admin transitions (a Propose/Finalize/Cancel pattern, a timelock, a multi-step state archival), the Quint protocol model and the adversarial review can fail to keep pace. The result: an attack class entirely outside the modeled state space.

**Proposed shape**: any contract revision that adds (a) a new admin transition, (b) a timelock, (c) a multi-tx Propose/Finalize/Cancel feature, or (d) a state archival triggers a lifecycle-adversary stage. The stage operator extends the Quint model to encode the new transitions, then Quint-adversarial generates counterexample traces against active-phase invariants over all multi-block sequences combining the new transitions with existing ones. Deliverable: `.colosseum/lifecycle-adversary/<feature>.md`.

**Recommended dogfood**: any v0.4 project that ships a contract feature beyond a single admin transition. Verified-rcv would have caught N17 by extending the Quint model and red-teaming the registry-rotation feature.

**Codified form (v0.4 target)**: **SHIPPED**: see `skills/colosseum-lifecycle-adversary/SKILL.md`.

### Ask AF — CI-self-test pre-merge gate

**Evidence**: verified-rcv v0.3.10 added 4 CI gates. Three of them (N18 cargo-audit RUSTSEC ignore, N19 mock_attestation regex false-positive on user-facing "verification" strings, N20 cosmwasm-check rejects raw cargo build) failed on the commit that added them. The auditor caught each one in subsequent rounds.

**Symptom this addresses**: CI gates added without local verification can ship broken because the gates only run after merge.

**Proposed shape**: any PR that adds a CI step must demonstrate the step passing at the commit that adds it. The simplest enforcement is a pre-merge check that runs the CI from the PR branch (which is the CI's job anyway, so this is enforcing the CI's own purpose rather than adding new tooling).

**Recommended dogfood**: any v0.4 project that ships CI infrastructure. Mostly a discipline ask, not a methodology ask, but worth documenting.

**Codified form (v0.4 target)**: `colosseum-compose/SKILL.md` CI sub-step gains an "added-CI-must-be-green-at-add-commit" rule.

### Ask AG — Commit-message vs code reconciliation pre-merge check

**Evidence**: verified-rcv N7 (R3 audit, Informational): the commit message claimed N4 was deferred while the code changed N4. Mechanical drift between intent stated in commit-message and the actual diff.

**Symptom this addresses**: commit-messages can claim things the diff does not deliver (and vice versa).

**Proposed shape**: lightweight pre-merge check. For every commit, parse the message for claims (e.g., "deferred", "implemented", "fixed N#"), grep the diff for the named entities, and flag mismatches. Most can be heuristic and human-reviewed; the goal is to surface the drift, not to gate strictly.

**Recommended dogfood**: any v0.4 project. Lightweight; mostly a discipline ask.

**Codified form (v0.4 target)**: `colosseum-change/SKILL.md` change-record schema documents the commit-message-vs-code field; a `scripts/check_commit_message.py` reference implementation provides the heuristic.

### Ask AH — Quint-adversarial as a separately-run stage with adversarial trace generation

**Evidence**: verified-rcv M1 (CreateElection clobbers in-flight election). Quint modeled the B1 write-once invariant correctly. Code drift was the CreateElection handler did not check the current phase. A Quint-adversarial pass generating counterexample traces against admin transitions would have produced trace `[CreateElection, SubmitBallot, CreateElection]` and asserted the second CreateElection is rejected. The Quint model had the predicate; nothing forced the trace generation.

**Symptom this addresses**: Quint-spec produces invariants but does not by itself produce attack traces. The adversarial pass against the Quint model is a separate methodology step from the spec construction.

**Proposed shape**: every Quint property gets an adversarial-trace generation pass. Output: a list of admissible trace prefixes that would violate the property if uncaught; cross-reference each trace against the contract code's enforcement.

**Recommended dogfood**: any v0.4 project that uses Quint for protocol-level invariants. Verified-rcv would have caught M1 here.

**Codified form (v0.4 target)**: **SHIPPED**: see `skills/colosseum-adversarial/SKILL.md` Step 4.5 (Quint-adversarial — separately-run trace generation).

### Ask AI — Field-spec discipline at intent-elicitation (wire-length pins on binary-data fields)

**Evidence**: verified-rcv M3 (EnclaveImageRegistry shape validation missing). Intent §6.1 named mrtd and rtmr as TDX measurements without pinning the wire length. The auditor surfaced that the registry stored mrtd as a hex string with no length constraint.

**Symptom this addresses**: intent prose can name a binary-data field by its semantic (TDX measurement, public key, hash) without committing to a wire format. Downstream code can then accept malformed wire values.

**Proposed shape**: intent-elicitation produces a field-spec table for every binary-data field with columns `(field, semantic, wire format, length, validation site)`. Every field with a non-bounded length is flagged for explicit decision.

**Recommended dogfood**: any v0.4 project. Verified-rcv would have caught M3 (and several minor findings in the same shape) here.

**Codified form (v0.4 target)**: `colosseum-intent/SKILL.md` template adds a "Field specifications" section with the table format.

---

## Carry-forward from v0.2

The v0.2 ask file at `quartz/.colosseum/methodology-v0.2-asks.md` is partially shipped; the remaining open items are inherited here:

- **v0.2 Asks 1–4** (original): documented form shipped in v0.2 commits; enforced form deferred behind executable-layer decision.
- **v0.2 Ask 5** (Round A strengthening — free-symbol detection at lift time): documented form ships in v0.2; enforced form pending.
- **v0.2 Asks 6–7** (cycle-6.4-through-6.11 implementation): per-conjunct failure-mode table + cycle-outcome intent enum. Documented form shipped in v0.3 (Ask 6 → `colosseum-compose` Step 3 sub-step; Ask 7 → `colosseum-change` Step 8 record schema). Enforced form pending.

**Executable-layer decision** (still open): the recurring "enforced form deferred" item across v0.2 and v0.3 asks is gated on a Colosseum architectural decision — does compose / change / adversarial run a programmatic check at the relevant step, or stay prose-only? The decision shape is documented in v0.2 asks; v0.4 continues to inherit the open question until it is decided.

---

## Validation criteria (per-candidate, for promotion to stable)

Each tentative candidate promotes from this file into a SKILL.md when its named dogfood project produces direct evidence that exercises the pattern. The general shape:

- **Ask I** (system-of-intents): bidboard run produces a multi-component intent decomposition. Promotion criterion: the decomposition is referenced by at least one adversarial pass and one compose-ledger entry.
- **Ask J** (per-section dispatch): a v0.4 adversarial run uses per-section dispatch and the synthesis correctly aggregates section-local findings. Promotion criterion: at least one finding from the run is cross-section (a finding that bridges sections) and is caught by aggregation rather than missed.
- **Ask K** (file-access subagent dispatch): a v0.4 run dispatches via OpenCode file-access subagents and the manifest correctly records per-voice file-access traces. Promotion criterion: a subagent reads a section that the inlined-prompt mode would not have included.
- **Ask L** (frontier-tier requirement): a v0.4 system-level run is dispatched with a documented frontier-tier panel. Promotion criterion: a system-level adversarial pass demonstrates a finding that only frontier voices surfaced.
- **Ask M** (assume-guarantee): bidboard's component intents carry assume/guarantee clauses and boundary docs record implication-links. Promotion criterion: a system-level conjunction theorem is recorded in the compose-ledger.
- **Ask N** (versioning): a v0.4 boundary doc is published with a SemVer pin against its component intents, and a re-verify pass correctly identifies drift (or its absence) using the version fields. Promotion criterion: a compose-ledger entry's `upstream_version_prior` is non-trivially used in change-record reasoning.

For Asks O–T, the evidence already exists (Round 3a continuation 2026-05-19); the promotion criterion is SKILL codification, not further dogfood:

- **Ask O** (cross-critique): codification lands in `colosseum-adversarial/SKILL.md` Step 6.5 with reference Q1/Q2/Q3 prompt template. Promotion criterion: a v0.4 project uses the codified step end-to-end.
- **Ask P** (defense round): codification lands in `colosseum-adversarial/SKILL.md` Step 6.6 with defend/concede/third-option protocol. Promotion criterion: a v0.4 defense round produces a structured concession via the codified protocol.
- **Ask Q** (encoding-discipline notes): codification lands in `colosseum-intent/SKILL.md` template Section 9 (or appendix). Promotion criterion: a v0.4 intent doc publishes encoding-discipline notes ahead of fan-out divergence (proactively), not just reactively.
- **Ask R** (re-cross-critique): codification lands in `colosseum-adversarial/SKILL.md` Step 6.7 with mandatory-after-load-bearing-revision trigger. Promotion criterion: a v0.4 project's re-cross-critique catches a revision-induced regression.
- **Ask S** (ghost-variable encoding): codification lands in spec-encoding section of `colosseum-adversarial/SKILL.md` Step 5 (or new `colosseum-spec-encoding` SKILL). Promotion criterion: a v0.4 spec uses ghost+invariant encoding for at least one freeze-at-time property, and a follow-up adversarial pass cites the pattern.
- **Ask T** (high reasoning default): codification lands in `colosseum-adversarial/SKILL.md` Step 4 dispatch table + `colosseum_run.py` manifest. Promotion criterion: a v0.4 manifest records per-voice `variant` field and the dispatch honors it across providers.
- **Ask U** (Lake project + Mathlib default): codification lands in `colosseum-intent/SKILL.md` (Lean spec layer setup step) and `colosseum-compose/SKILL.md` (ledger references Lake project root). Promotion criterion: a v0.4 crypto-touching project's Lean spec layer is set up as a Lake project with Mathlib + VCV-io from the start, and the ledger entry references the Lake root.
- **Ask V** (lean-lsp Mathlib hang): codification lands in `colosseum-adversarial/SKILL.md` Step 4 troubleshooting block + an upstream issue filed against the lean-lsp MCP server. Promotion criterion: a v0.4 Lean dispatch project uses `lake env lean <file>` (or a fixed lean-lsp MCP) without the agent loop hanging on Mathlib snippets.
- **Ask W** (Lean discharge voice ranking): codification lands in `colosseum-compose/SKILL.md` "Voice selection for Lean discharge" sub-step. Promotion criterion: a v0.4 project's Lean discharge run uses the documented voice ranking (Claude primary, Leanstral secondary, single-shot frontier API as third) and produces clean proofs without the per-attempt friction observed in Round 3a continuation.

Until a candidate is promoted, dogfood projects MAY adopt the pattern locally; the methodology does not yet require it.
