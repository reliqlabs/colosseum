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

**2. Multi-model adversarial generation.** One model produces, another attacks. Different model families have different blind spots; combining them gives additive coverage. Crucially, *adversarial beats consensus* — multiple models agreeing can converge on shared wrongness, but an adversary's job is to find faults. This is the sharper version of "multi-model."

The `colosseum-adversarial` SKILL dispatches attacks and spec authoring across multiple channels. The primary fan-out mechanism is **OpenCode CLI direct dispatch**: each voice runs via `opencode run --agent <agent-name> --model <provider/model> --variant high`, with OpenCode handling provider connections to Anthropic, OpenAI, Google, Mistral cloud, an operator-curated gateway (Moonshot kimi-k2-6, NVIDIA nemotron-3-120b-a12b, Anthropic claude-opus-4-7 routed via Cloudflare), and local LM Studio models. Project-local agents under `<project>/.opencode/agent/` build from canonical bodies at `colosseum/agents/*-body.md` (rebuilt via `scripts/install-agents.py build`). The Claude voice runs natively in-harness (Agent subagent with file access). The `external-model-mcp` MCP server is retained for adhoc single-shot cloud queries that don't need a full agent loop, but is no longer the primary fan-out mechanism.

Routine milestones default to Claude + local + 1–2 gateway voices; system-scale milestones require frontier-tier voices across multiple families. The full loop runs: fan-out → synthesis → cross-critique → defense → fix → re-cross-critique → encoding-discipline back-propagation to intent.

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

Methodology validation runs against real projects. Each one produces concrete evidence — adversarial reports, ledger entries, methodology improvement proposals — that drives the next iteration.

| Project | Scope | Status |
|---|---|---|
| Quartz | TDX + zkdcap attestation primitives; Lean trust-boundary refactor; 8 protocol lifts | Mature; multi-cycle adversarial-driven tightening of the spec surface ongoing |
| verified-rcv | Instant-runoff voting CosmWasm contract + TDX enclave tabulation; greenfield methodology validation | Spec layer complete (intent → Quint → Lean → integration ledger); contract / enclave / frontend deferred |
| bidboard | Sponsorship-auction contract with anti-sniping; first multi-component dogfood | Planned — first test of the system-of-intents shape |

Each project's evidence base lives under its own `.colosseum/attacks/`, `.colosseum/changes/`, and `.colosseum/ledger.md`. Improvements that surface flow into the relevant SKILLs / docs once they've been exercised in anger; proposals awaiting validation are tracked in `methodology-improvements.md`. External literature backing them is catalogued in `references.md`.

## Status

Methodology in active development. The current shape — five pillars, the verification pyramid, the ten-stage workflow — is stable. SKILLs and MCPs are wired end-to-end on macOS Apple Silicon; new improvements arrive from dogfood projects and land in the SKILLs once they've been exercised in anger.

Improvement proposals awaiting validation live in [methodology-improvements.md](./methodology-improvements.md). The external literature they draw on is catalogued in [references.md](./references.md). Naming and vocabulary conventions are in [CONCEPTS.md](./CONCEPTS.md).

### Agentic backbone

| Component | Type | Path |
|---|---|---|
| `goedel-mcp` | MCP server | `mcp/goedel-mcp/` |
| `kani-mcp` | MCP server | `mcp/kani-mcp/` |
| `verus-mcp` | MCP server | `mcp/verus-mcp/` |
| `aeneas-mcp` | MCP server | `mcp/aeneas-mcp/` |
| `quint-mcp` | MCP server | `mcp/quint-mcp/` |
| `external-model-mcp` | MCP server (single-shot cloud queries; primary fan-out is OpenCode) | `mcp/external-model-mcp/` |
| `lm-studio-mcp` | MCP server (local model layer) | `mcp/lm-studio-mcp/` |
| `colosseum-spec-adversary` | Subagent (spec attack; canonical body + per-harness wrappers) | `agents/spec-adversary-body.md` |
| `colosseum-quint-spec-generator` | Subagent (Quint spec authoring loop) | `agents/quint-spec-generator-body.md` |
| `colosseum-failure-classifier` | Subagent (verification-failure triage) | `agents/colosseum-failure-classifier.md` |
| `colosseum-intent` | SKILL (intent elicitation, forward) | `skills/colosseum-intent/` |
| `colosseum-reverse-intent` | SKILL (intent distillation from existing code) | `skills/colosseum-reverse-intent/` |
| `colosseum-adversarial` | SKILL (multi-voice spec attack + Quint trace generation) | `skills/colosseum-adversarial/` |
| `colosseum-code-adversarial` | SKILL (read implementation against intent through six lenses) | `skills/colosseum-code-adversarial/` |
| `colosseum-lifecycle-adversary` | SKILL (multi-tx admin-feature red-team via Quint) | `skills/colosseum-lifecycle-adversary/` |
| `colosseum-verify` | SKILL (run the verification pyramid) | `skills/colosseum-verify/` |
| `colosseum-compose` | SKILL (trust ledger + axiom inventory + code-citation CI gate) | `skills/colosseum-compose/` |
| `colosseum-change` | SKILL (upstream-first change loop) | `skills/colosseum-change/` |
| `install-agents.py` | Build tool (regenerate per-harness wrappers from canonical bodies) | `scripts/install-agents.py` |
| `colosseum_run.py` | Manifest dispatch coordinator (reference shape; per-project scripts use the same schema) | `scripts/colosseum_run.py` |
| Coverage dashboard CLI | Deterministic tool | deferred |

This README is the working specification of the process itself.
