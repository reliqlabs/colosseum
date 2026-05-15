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

Until a candidate is promoted, dogfood projects MAY adopt the pattern locally; the methodology does not yet require it.
