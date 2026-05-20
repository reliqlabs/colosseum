# Colosseum

## Forged in the fire of adversity

A methodology for building dependable software in a world of fast, unreliable LLM workers.

This is not a product. It is a process — an attempt to develop the practice of producing software whose correctness is *mechanically* trustworthy, while preserving the speed and breadth that frontier LLMs bring. The first concrete output will be a small Rust program built end-to-end through this process to validate the approach on real code.

## Installing

See **[INSTALL.md](./INSTALL.md)** for full step-by-step instructions. Colosseum composes existing verification tools (Kani, Verus, Aeneas+charon, Quint+Apalache, Lean 4 + mathlib) through MCP wrappers, plus OpenCode CLI for multi-voice spec authoring and adversarial fan-out across cloud providers (OpenAI, Google, Mistral, Anthropic gateway) and local LM Studio models. Setup is incremental — each tool is optional, and each MCP's health check reports gracefully if its underlying tool is missing.

Tested on **macOS 14+ Apple Silicon**. Linux should mostly work; Windows is untested.

## Why

LLMs are fast, broad, and characteristically unreliable. Even frontier models at high effort make silly, recoverable mistakes: hallucinated APIs, subtle reasoning errors, plan drift, confident-wrong answers. Traditional correctness mechanisms — code review, human-written tests, manual audit — are human-bottlenecked and scale linearly with reviewer attention. LLM output scales 10–100× faster. That mismatch is the trust gap.

The thesis behind Colosseum: **correctness mechanisms must mechanize to match production velocity.** Don't slow LLMs down. Build automated trust layers underneath them.

The core invariant: *don't trade correctness for speed; mechanize correctness to match speed.*

## The five pillars

Colosseum composes five complementary trust mechanisms. None alone is sufficient; together they form a defense-in-depth stack where each layer prunes what the next must handle.

**1. Formal verification.** Mechanistic, composable, produces real guarantees rather than statistical confidence. Limit: can only verify what's specifiable; intent still requires human anchoring.

**2. Multi-model adversarial generation.** One model produces, another attacks. Different model families have different blind spots; combining them gives additive coverage. Crucially, *adversarial beats consensus* — multiple models agreeing can converge on shared wrongness, but an adversary's job is to find faults. This is the sharper version of "multi-model." **Current implementation status:** `colosseum-adversarial` (v0.3 evidence base, with v0.4 cross-critique + defense + re-cross-critique cycles validated in Round 3a continuation) dispatches attacks and spec authoring across multiple channels. The primary fan-out mechanism is **OpenCode CLI direct dispatch**: each voice runs via `opencode run --agent <agent-name> --model <provider/model> --variant high`, with OpenCode handling provider connections to Anthropic, OpenAI, Google, Mistral cloud, an operator-curated gateway (Moonshot kimi-k2-6, NVIDIA nemotron-3-120b-a12b, Anthropic claude-opus-4-7 routed via Cloudflare), and local LM Studio models. Project-local agents distributed under `<project>/.opencode/agent/` build from canonical bodies at `colosseum/agents/*-body.md` (rebuilt via `scripts/install-agents.py build`). Reference dispatch scripts at `verified-rcv/.colosseum/scripts/*_dispatch.py` cover fan-out, cross-critique, defense, and re-cross-critique on both Quint and Lean layers. The Claude voice runs natively (Agent subagent with file access). The earlier `external-model-mcp` MCP server is retained as a path for adhoc single-shot cloud queries that don't need the full agent loop, but is no longer the primary fan-out mechanism. Routine milestones default to Claude + local + 1–2 gateway voices; system-scale milestones require frontier-tier voices across multiple families. Round 3a-validated workflow: fan-out → synthesis → cross-critique → defense → fix → re-cross-critique → encoding-discipline back-propagation to intent.

**3. Mechanistic constraints in the substrate.** Pre-LLM-era tools — types, ownership, linters, sanitizers — are underrated when paired with LLM output. Rust's type system rejects whole classes of bugs silently. Cheap, deterministic, no model required.

**4. Empirical validation at scale.** Property-based testing, fuzzing, bounded model checking. Statistical confidence on input regions formal methods can't reach. Property-based tests bridge specs and code as cheaply as anything in the stack.

**5. Boundary discipline.** Narrow interfaces between trusted (verified) and untrusted (probabilistic) regions of the codebase. LLM-generated code lives behind verified boundaries. The verified core is small and deeply guaranteed; the periphery is contained by it. The *shape* of the codebase determines whether verification effort compounds or scatters.

## The deepest claim

> In a world of fast unreliable workers, the unit of trust is not consensus — it is surviving adversarial scrutiny.

Most agent systems being built today default to cooperative multi-agent patterns: agents that help, vote, converge. That is the wrong primitive for *correctness*. Cooperation amplifies shared mistakes. Adversaries hunt them. Colosseum treats antagonistic generation as a first-class primitive of the development loop.

## The verification pyramid

Each property a program must hold is routed to the cheapest tool that can verify it. Two axes, not one: a **spec axis** that runs upstream of code, and an **exec axis** that runs against real Rust. The two compose — system-level specs from the spec axis become refinement targets for the exec axis.

**Exec axis** (against real Rust, cheap → expensive):

```
                  Aeneas → Lean         ← deep theorem proofs over extracted Rust
                  Verus                 ← SMT-backed Rust verification
                  Kani                  ← bounded model checking
                  Property tests        ← random/structured behavioral sweeps
                  Fuzzing               ← panic/crash discovery
                  Clippy / lints        ← pattern detection
                  Types                 ← mechanical bug-class rejection
```

**Spec axis** (upstream of code, used when system-level reasoning is required):

```
                  Lean (math, refinement)   ← deep correctness theorems, cross-component composition
                  Quint / TLA+              ← protocol & state-machine model checking
```

Spec-axis artifacts are written *before* the Rust they constrain. Their job is to make the intent precise enough that exec-axis tools can check the implementation against it. Quint catches protocol bugs at the architecture stage; Lean math captures cross-component theorems that no single exec-axis tool can see (e.g. enclave commitment + contract discipline + ECIES roundtrip + attestation soundness as one trust claim).

Wide cheap base on each axis; narrow expensive top. Cheap layers do most of the work. Expensive layers only see what cheaper ones could not handle.

## The workflow

The process moves through stages. Each stage produces an artifact that anchors the next.

1. **Intent document.** Human-written. The single source of truth. Behaviors, invariants, failure modes, non-goals, trust boundaries, scenarios. Quality of everything downstream is bounded by quality of this document. Two authoring modes: **elicitation** (forward, before code — `colosseum-intent`) and **distillation** (backward, from existing code + docs + commits — `colosseum-reverse-intent`). The document's structure is designed to make contradictions visible: structured behavior blocks force pre/post-condition triples, behavioral invariants must be tagged `state` or `temporal`, and the cross-section consistency check is a mechanical sweep over the structure rather than a freeform read.
2. **Tracer-bullet prototype.** Fast, ugly, throwaway Rust that proves the design is feasible. Insurance against over-constrained specs. **Explicit discard gates** — a tracer is discarded, not promoted, when *any* of: Aeneas cannot extract its surface area; the design needed more than two fundamental restructures during the tracer phase; the final interface footprint is more than double the intent v1 surface; performance is off-target by more than 10× and the design has no headroom. If none of those gates trip, the tracer probably *is* the v1 — name it honestly and revise intent to match, rather than pretending a throwaway happened.
3. **Intent v2.** Revised with what the prototype revealed.
4. **System-level specification.** Quint or TLA+ for behavioral/protocol properties (only when distributed or concurrent semantics matter).
5. **Implementation-level specification.** Lean specs and/or Verus annotations derived from intent and system spec.
6. **Adversarial spec validation.** Multiple models draft specs independently. A separate model attacks each draft, searching for ways it under- or over-constrains the intent. Specs survive when they survive scrutiny — not when they agree.
7. **Implementation.** Rust written against the validated specs. Designed for verifiability: pure cores, narrow effects, explicit state.
8. **Verification.** The pyramid runs continuously. Types first, then lints, then property tests, then fuzz, then Kani, then Verus, then Aeneas → Lean.
9. **Failure classification.** When verification fails: spec wrong, code wrong, or prover stuck. Route accordingly. Loud failure beats silent success.
10. **Coverage dashboard.** Per function: proven, tested-only, or unverified. Trust is calibrated to coverage, not to vibes.

## What this is and isn't

What Colosseum is:
- A response to the velocity-correctness mismatch in LLM-assisted development
- A way to use LLMs at full output without inheriting their failure modes
- A methodological shift in how software gets built, not only how it gets tooled

What Colosseum is not:
- A way to verify intent — humans still own "what should this do"
- A way to remove humans entirely — escalation queues stay staffed
- Cheap — tokens, compute, and setup costs are real
- A solution for truly novel design — verification needs anchored notions of "correct"

## Tooling stack

Initial target stack (Rust ecosystem):

| Layer | Tool | Purpose |
|-------|------|---------|
| Types | Rust compiler | Mechanical bug-class rejection |
| Lints | Clippy | Pattern detection |
| Property tests | `proptest` | Behavioral exploration |
| Fuzzing | `cargo-fuzz` | Panic/crash discovery |
| Bounded MC | Kani | Property checking with bounded loops |
| SMT verification | Verus | Annotation-driven Rust verification |
| Code → proof | Aeneas (primary) / hax (alternative) | Rust → Lean (Aeneas) or Rust → F\* (hax) translation |
| Theorem proving | Lean 4 + mathlib | Deep correctness proofs |
| Cryptographic foundations | [VCV-io](https://github.com/Verified-zkEVM/VCV-io) | Foundational Lean 4 crypto library — `OracleComp`, `ProbComp`, relational program logic, NIST PQC primitives |
| SNARK / IOR foundations | [ArkLib](https://github.com/Verified-zkEVM/ArkLib) | Formalized SNARKs over IORs (sum-check, Spartan, FRI, STIR, WHIR, Binius); track for projects using these schemes |
| Protocol spec | Quint | State-machine and temporal properties |
| Proof specialist | Goedel Prover V2 | Lean tactic proposal (local) |
| Lean integration | `lean-lsp-mcp` | Proof state, mathlib search, diagnostics |
| Orchestration | Claude Code (primary harness) | Planning, error recovery, failure routing, single-voice agent dispatch via the Agent tool |
| Multi-voice dispatch | OpenCode CLI (`opencode run --agent ... --model ... --variant high`) | Project-local agent dispatch across cloud providers + gateway + local LM Studio; used for adversarial fan-out, cross-critique, defense rounds, re-cross-critique. Reference dispatch scripts under `verified-rcv/.colosseum/scripts/*_dispatch.py` |

Model selection follows the same principle as tool selection: cheapest model that can handle the job, with adversarial pairing on critical outputs.

## Related work

This methodology builds on existing work and stays current with adjacent published efforts.

- **VCVio: Verified Cryptography in Lean via Oracle Effects and Handlers** (Tuma, Dao, Waters, Hicks, Hopper; [eprint 2026/899](https://eprint.iacr.org/2026/899)). Foundational Lean 4 framework for cryptographic proofs using algebraic effects + handlers. Closest published peer to Colosseum's methodology stance — explicitly reports on LLM-assisted theorem proving as a data point, including workflows and failure modes. Adopt VCV-io as the Lean substrate for any crypto-touching Colosseum project; it replaces axiomatic stubs (the kind cataloged in a project's integration ledger) with mechanically discharged oracle models.
- **ArkLib** (Verified-zkEVM, 2025–). Modular SNARK / IOR formalization on top of VCV-io. Active targets: sum-check, Spartan, Merkle trees, FRI, STIR, WHIR, Binius. Not yet covering Groth16 / PLONK / STARKs. Track for projects using FRI-style proof systems.
- **Aeneas (Charon + Aeneas)** vs **[hax](https://github.com/hacspec/hax)** as Rust-extraction paths. Aeneas targets Lean 4 / Coq / F\* / HOL4; hax targets F\* primarily, with experimental Coq/Lean. Colosseum defaults to Aeneas → Lean for the theorem-proving layer; hax + F\* is a legitimate alternative for users whose toolchain is already F\*-anchored (e.g. HACL\*, miTLS). Tradeoff: Aeneas's Lean targeting composes naturally with mathlib and VCV-io; hax has stronger production-scale adoption in HACL\* and Bertie. ArkLib's roadmap mentions hax as its Rust-extraction path of choice.

## Dogfood projects

Methodology validation runs against real projects ("dogfood"), recorded as Rounds. Each round produces concrete evidence — adversarial reports, ledger entries, methodology asks — that drives the next methodology version.

| Round | Project | Scope | Status |
|---|---|---|---|
| 1 | Quartz (TDX + zkdcap attestation primitives) | Lean trust-boundary refactor; 8 `_negl` protocol lifts | Steps 1-7 complete; cycle-6.4-through-6.11 def-tying refactor landed 2026-05-14 |
| 2 | Quartz Round A adversarial review | Multi-model attack on the 8 lifts | Returned BREAKS; surfaced v0.2 Asks 5, 6, 7 |
| 3a | `verified-rcv` (instant-runoff voting CosmWasm contract + TDX enclave tabulation) | Greenfield methodology validation: intent → adversarial → multi-voice fan-out → cross-critique → defense → re-cross-critique → encoding-discipline back-propagation → Lean spec → ledger | **Closed 2026-05-20**. Intent v0.3.3, Quint canonical, Lean canonical, integration ledger all complete. Spec-layer only (no contract / enclave / frontend this cycle). Comparator pivoted to deferred (no external IRV reference to compare against; upstream Quartz has no ranked-choice example). Asks O–T back-ported to v0.4 candidates. |
| 3b+ | Bidboard (sponsorship-auction contract with anti-sniping, multi-component) | Planned first multi-component dogfood; first test of system-of-intents shape | Pending |

Each round's evidence base lives under the dogfood project's `.colosseum/attacks/`, `.colosseum/changes/`, and `.colosseum/ledger.md`. The methodology asks they surface flow into the relevant SKILLs / docs once stable; tentative candidates awaiting dogfood validation are tracked in `methodology-v0.{N}-candidates.md` files in this repo.

Round 3a's combined evidence shipped as v0.3: 8 stable asks back-ported into SKILLs / docs (gateway provider, per-route timeout caveats, theorem-prover exclusion, LM Studio contention discipline, manifest-protocol dispatch, voice-failure-mode catalog, overlap-matrix synthesis, voice diversity metadata) + 12 tentative candidates tracked in `methodology-v0.4-candidates.md` (6 from pattern survey, 6 from Round 3a continuation dogfood). The external sources Round 3a's pattern survey rests on are catalogued in `references.md`.

## Status

Methodology in development. **Round 3a dogfood (`verified-rcv`) closed 2026-05-20**: greenfield methodology validation on an IRV protocol target produced an intent doc (v0.3.3, 8 revision cycles), Quint protocol spec, Lean math spec, integration ledger, and a multi-cycle adversarial trail (fan-out → cross-critique → defense → re-cross-critique → encoding-discipline back-propagation). Scope was spec-layer only (no Rust crate this cycle). Asks O–T from the continuation are appended to the v0.4 candidate set.

**Methodology versioning** (this repo): v0.2 set surfaced from Quartz Round A is partially shipped (documented form; enforced form gated on the executable-layer decision); v0.3 set surfaced from Round 3a is split into stable (back-ported into SKILLs / docs) and tentative (tracked in `methodology-v0.4-candidates.md`). v0.4 candidate set now spans 12 asks: I–N from pattern survey + O–T from Round 3a continuation (cross-critique standard step, defense round protocol, encoding-discipline intent-tightening as convergence lever, re-cross-critique after canonical revision, ghost-variable encoding for action-guard-only invariants, `--variant high` reasoning default). External pattern-survey sources are catalogued in `references.md`.

v1 agentic backbone:

| Component | Type | Status | Path |
|-----------|------|--------|------|
| goedel-mcp | MCP server | v0.1 (✓ stdio-validated, Goedel V2 32B reachable via LM Studio). **Methodology note**: goedel-class models excluded from adversarial spec review per v0.3 Ask C — verify-pyramid use only. | `mcp/goedel-mcp/` |
| kani-mcp | MCP server | v0.1 (✓ stdio-validated, cargo-kani 0.67.0; 41/41 Quartz harnesses discovered) | `mcp/kani-mcp/` |
| verus-mcp | MCP server | v0.1.1 (✓ stdio-validated, Verus 0.2026.05.05; comment-FP bug fixed) | `mcp/verus-mcp/` |
| aeneas-mcp | MCP server | v0.1.2 (✓ end-to-end: Rust→LLBC→Lean pipeline; `--preset=aeneas`, `-backend` flags fixed, `rocq` backend added, `.lake/` exclusion) | `mcp/aeneas-mcp/` |
| quint-mcp | MCP server | v0.1 (✓ end-to-end: quint 0.32.0 + Quartz handshake.qnt run completed 3704 traces/sec, 22/22 invariants discovered) | `mcp/quint-mcp/` |
| external-model-mcp | MCP server | v0.2 (Round 3a-validated; OpenAI + Gemini single-shot + fan-out + gateway channel; `.env`-loaded credentials, no URLs/tokens in code). **Superseded for primary fan-out**: as of Round 3a continuation (2026-05-20), multi-voice fan-out runs through OpenCode CLI direct dispatch instead of `external-model-mcp` fan-out. The MCP is retained for adhoc single-shot cloud queries from within Claude Code that don't need an agent loop. See `gateway-bugs-2026-05-14.md` for known route failure modes. | `mcp/external-model-mcp/` |
| lm-studio-mcp | MCP server | v0.1 (✓ stdio-validated; cross-session contention discipline documented in v0.3 Ask D — use `lms load` before dispatch + retry-on-unload) | `mcp/lm-studio-mcp/` |
| colosseum-spec-adversary | Subagent | **v0.2** (+ `temporal_state_mismatch` category, + slice-aware vs full-spec invocation modes, + canonical-body + per-harness-wrapper distribution). Canonical body at `agents/spec-adversary-body.md`; per-harness wrappers at `agents/colosseum-spec-adversary.md` (Claude Code) and `agents/opencode/spec-adversary.md` (OpenCode). | `agents/spec-adversary-body.md` |
| colosseum-quint-spec-generator | Subagent | **v0.1** (canonical body + per-harness wrappers; iterates with the typechecker until rcv.qnt + main.qnt + design-notes.md pass quint typecheck + all_invariants + reachability witnesses). Canonical body at `agents/quint-spec-generator-body.md`; wrappers at `agents/colosseum-quint-spec-generator.md` (Claude Code) and `agents/opencode/quint-spec-generator.md` (OpenCode). | `agents/quint-spec-generator-body.md` |
| install-agents.py | **Build tool (new in v0.3+)** | ✓ regenerates per-harness wrappers from canonical bodies. Run after editing any `agents/*-body.md`. | `scripts/install-agents.py` |
| colosseum-failure-classifier | Subagent | v0.1.1 (+ `state_space_blowup` category) | `agents/colosseum-failure-classifier.md` |
| `colosseum-intent` | Skill | v0.2 (elicitation mode; structured behavior blocks + state/temporal invariant tagging). v0.4 candidate extension for system-of-intents shape (Ask I in `methodology-v0.4-candidates.md`). | `skills/colosseum-intent/` |
| `colosseum-reverse-intent` | Skill | v0.2 (distillation mode; same structural discipline applied retroactively) | `skills/colosseum-reverse-intent/` |
| `colosseum-adversarial` | Skill | **v0.3** (Round 3a-validated: gateway channel + per-route timeout caveats + theorem-prover specialist exclusion + ops notes on cross-session contention + harness-agnostic manifest forward-pointer) | `skills/colosseum-adversarial/` |
| `colosseum-verify` | Skill | v0.1 (untested end-to-end; Round 3a closed without exercising it since the cycle was spec-layer-only with no Rust crate. Next dogfood with a real Rust target — Bidboard Round 3b+, or a future verified-rcv implementation cycle — will exercise it). | `skills/colosseum-verify/` |
| `colosseum-compose` | Skill | v0.1 (cross-component theorems + integration ledger + axiom inventory). v0.4 candidate extension for spec-version tracking (Ask N in `methodology-v0.4-candidates.md`). | `skills/colosseum-compose/` |
| `colosseum-change` | Skill | v0.1 (change-loop: triage → intent diff → impact → upstream-first revisions → re-verify → composition re-check). v0.2 candidate extension for cycle-outcome-intent enum per v0.2 Ask 7. | `skills/colosseum-change/` |
| `colosseum_run.py` | Manifest tool (v0.3 prototype) | ✓ prototype; harness-agnostic dispatch coordinator; exercised on retrofitted Round 3a run dir. **Note**: in Round 3a continuation work the practical dispatch shape became direct OpenCode CLI invocation via per-project Python scripts (`verified-rcv/.colosseum/scripts/*_dispatch.py`). `colosseum_run.py`'s manifest schema remains the reference contract; the dispatch scripts produce manifest-compatible output. | `scripts/colosseum_run.py` |
| `references.md` | **Source register (new in v0.3)** | ✓ comprehensive; 9 sections covering decomposition / compositional verification / long-context LLMs / spec versioning / tooling / domain / internal artifacts | `references.md` |
| `methodology-v0.4-candidates.md` | **Tentative-asks register (new in v0.3)** | ✓ 12 v0.4 candidates: 6 from pattern survey (I = system-of-intents shape, J = per-section dispatch, K = file-access subagent dispatch, L = frontier-tier requirement, M = assume-guarantee inter-component invariants, N = SemVer + compose-ledger versioning) + 6 from Round 3a continuation dogfood (O = cross-critique, P = defense round, Q = encoding-discipline intent-tightening, R = re-cross-critique, S = ghost-variable encoding, T = `--variant high` reasoning default). v0.3 stable asks back-ported into SKILLs / docs and indexed in this file's lookup table. | `methodology-v0.4-candidates.md` |
| coverage dashboard CLI | Deterministic tool | deferred to v1.1 | `tools/` |

This README is the working specification of the process itself. Round 3a closed 2026-05-20; the v0.3 stable ask set has landed in SKILLs / docs, and the v0.4 candidate set is documented in `methodology-v0.4-candidates.md` awaiting Round 3b validation.
