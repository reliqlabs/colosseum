# Colosseum methodology — references

Source register for the Colosseum methodology. External sources cited or surfaced during methodology development; internal artifacts produced by dogfood projects (Quartz, verified-rcv); tooling references the methodology depends on.

Maintained to support: (a) honest provenance for methodology claims, (b) external review / academic discussion, (c) reproducibility of methodology evidence, (d) traceability for back-ports from dogfood projects into SKILLs.

**Discipline:** every external claim in a SKILL.md, agent prompt, or skill-emitted artifact should be traceable to an entry here. Internal artifacts (per-project dogfood evidence) are cited inline; this file collects the *external* substrate the methodology rests on.

---

## A. Multi-component / system-of-intents decomposition

The pattern Colosseum's system-of-intents shape inherits from.

| Topic | Source | Why it matters to Colosseum |
|---|---|---|
| TLA+ EXTENDS vs INSTANCE (module structure) | [The Module Structure of TLA+ — Leslie Lamport](https://lamport.azurewebsites.net/tla/newmodule.html) | Distinguishes "logically one spec, split for readability" (EXTENDS) from "parameterized instance of a generic module" (INSTANCE M WITH …). Direct analogue for system-of-intents shape: component intents EXTEND a shared schema; boundary docs INSTANCE component contracts with explicit `WITH` parameter binding. |
| TLA+ multi-spec composition | [Composing TLA+ Specifications with State Machines — Hillel Wayne](https://www.hillelwayne.com/post/composing-tla/) | Practical guide to composing several state machines into a system spec. Validates the pairwise-relationship pattern with explicit parameterization. |
| TLA+ module ordering (read order matters) | [TLA+ in Practice and Theory Part 4: Order in TLA+ — pron](https://pron.github.io/posts/tlaplus_part4) | Cautions on module-order dependencies in compositional spec — applies to Colosseum compose-ledger dependency ordering. |
| seL4 layered specification | [seL4: Formal Verification of an OS Kernel — Klein et al. (CACM)](https://cacm.acm.org/research/sel4-formal-verification-of-an-operating-system-kernel/), [PDF version](https://trustworthy.systems/publications/nicta_full_text/1852.pdf), [Comprehensive Formal Verification of an OS Microkernel — seL4 expanded](https://sel4.systems/Research/pdfs/comprehensive-formal-verification-os-microkernel.pdf) | Three-layer formal spec (abstract Isabelle/HOL ← Haskell executable ← C impl), connected by refinement theorems. Pattern for vertical decomposition (intent → spec → code) that Colosseum already implicitly uses. |
| Domain-Driven Design — Bounded Context | [bliki: Bounded Context — Martin Fowler](https://martinfowler.com/bliki/BoundedContext.html), [Strategic DDD by Example: Bounded Contexts Mapping — Jarek Orzel](https://levelup.gitconnected.com/strategic-ddd-by-example-bounded-contexts-mapping-d94ffcd45954), [Context Mapper](https://contextmapper.org/) | Each component owns its model; cross-component relationships are first-class. Five relationship patterns: Customer/Supplier, Open Host Service, Published Language, Anti-Corruption Layer, Shared Kernel. Colosseum boundary docs adopt this taxonomy. |
| CompCert phased compilation | [The structure of CompCert — AbsInt](https://www.absint.com/compcert/structure.htm), [Formal Verification of a Realistic Compiler — Leroy / CACM](https://cacm.acm.org/research/sel4-formal-verification-of-an-operating-system-kernel/) | 15 phases / 8 intermediate languages, each with operational semantics + semantic-preservation theorem. Evidence that the "abstract layer also has internal structure" pattern scales to real systems. |
| Lean 4 modules + namespaces | [Source Files and Modules — Lean 4 reference](https://lean-lang.org/doc/reference/latest/Source-Files-and-Modules/), [Namespaces and Sections — Lean 4](https://lean-lang.org/doc/reference/latest/Namespaces-and-Sections/) | Modules vs namespaces are orthogonal — modules are compilation units with public/private scope; namespaces organize names. Colosseum compose-ledger's per-theorem provenance benefits from this separation. |
| Architecture Decision Records | [adr.github.io](https://adr.github.io/), [Architecture Decision Record — Martin Fowler](https://martinfowler.com/bliki/ArchitectureDecisionRecord.html), [Microsoft Azure Well-Architected — ADR guide](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record), [GitHub examples — joelparkerhenderson/architecture-decision-record](https://github.com/joelparkerhenderson/architecture-decision-record) | Per-decision artifact with status field (proposed/accepted/superseded), captures cross-cutting decisions that don't fit any single intent. Colosseum's `decisions/` directory pattern. |

## B. Compositional verification (rely-guarantee / assume-guarantee reasoning)

The mathematical foundation for "system safety = conjunction of local invariants" beyond pairwise relationships.

| Topic | Source | Why it matters to Colosseum |
|---|---|---|
| Rely-Guarantee reasoning (foundational) | [A Rely-Guarantee-Based Simulation for Verifying Concurrent Program Transformations — Liang, Feng, Fu (POPL 2012)](https://hongjin-liang.github.io/papers/popl12-rgsim.pdf), [TOPLAS 2014 extended](https://cs.nju.edu.cn/xyfeng/research/publications/TOPLAS14_Preprint.pdf) | Each component verified in isolation under an assumption about its environment, with a guarantee about its own behavior. Two components compose if A's guarantee implies B's rely. Foundational to non-pairwise composition. |
| CSim² compositional top-down verification | [CSim²: Compositional Top-down Verification of Concurrent Systems using Rely-Guarantee — ACM TOPLAS Vol 43, No 1](https://dl.acm.org/doi/fullHtml/10.1145/3436808) | Concrete Isabelle/HOL framework for rely-guarantee composition. Pattern for tooling Colosseum compose-ledger could adopt at the Lean layer. |
| Compositional inductive invariant inference (2025) | [Compositional Inductive Invariant Inference via Assume-Guarantee Reasoning — Dardik & Kang, 2025](https://arxiv.org/abs/2509.06250), [PDF](https://arxiv.org/pdf/2509.06250) | **Most recent work — directly relevant.** Per-component A/G contracts + local inductive invariants → system-wide safety by conjunction. Resolves the "pairwise specs explode exponentially" worry: O(n) contracts + O(boundaries) docs + 1 system-conjunction theorem suffices. |
| Component-based system verification (BIP) | [Compositional Verification for Component-based Systems and Application — Sifakis et al. (Verimag)](https://www-verimag.imag.fr/~sifakis/RecentPublications/2010/iet-sen.pdf) | BIP (Behavior-Interaction-Priority) framework: atomic components are automata with data + functions, parallel composition parameterized by n-ary interactions. Pattern for >2-way invariants. |
| Symbolic A-G with learning | [Learning-based Symbolic Assume-guarantee Reasoning — Alur et al. (ATVA 2006)](https://www.cis.upenn.edu/~alur/ATVA06.pdf) | Automatic generation of contract assumptions via L*-style learning. Suggests a pattern where missing assume-clauses can be inferred rather than authored. |
| Rely-guarantee for real-world OS (Zephyr) | [Rely-Guarantee Reasoning About Concurrent Memory Management in Zephyr RTOS — Springer LNCS](https://link.springer.com/chapter/10.1007/978-3-030-25543-5_29) | Production evidence that rely-guarantee scales to real systems (not just toy examples). |

## C. Long-context LLM evaluation & multi-document review

Empirical limits and behaviors of long-context LLMs — relevant to adversarial-review-at-scale capacity planning.

| Topic | Source | Why it matters to Colosseum |
|---|---|---|
| ∞Bench (>100K token eval) | [∞Bench: Extending Long Context Evaluation Beyond 100K Tokens — Zhang et al. (ACL 2024)](https://aclanthology.org/2024.acl-long.814/), [HTML version](https://arxiv.org/html/2402.13718v1) | First standardized benchmark for >100K context. Establishes that capacity ≠ effective use. |
| LoCoBench (10K–1M token code tasks) | [LoCoBench: A Benchmark for Long-Context Large Language Models](https://arxiv.org/pdf/2509.09614), [LoCoBench-Agent](https://arxiv.org/pdf/2511.13998) | Codebase-scale evaluation. Validates that long-context capacity is needed for real-system reasoning. |
| Context rot — performance degrades with input length | [Context Rot: How Increasing Input Tokens Impacts LLM Performance — Chroma research](https://research.trychroma.com/context-rot) | **Critical methodological observation.** Models do not use context uniformly; reliability decreases as input length grows. Justifies per-section dispatch + file-access subagent patterns over inline-everything dispatch. |
| BABILong (long-context reasoning) | [BABILong: Testing the Limits of LLMs with Long Context Reasoning-in-a-Haystack — NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/file/c0d62e70dbc659cc9bd44cbcf1cb652f-Paper-Datasets_and_Benchmarks_Track.pdf) | Reasoning-in-a-haystack pattern — needle-finding ≠ multi-document reasoning. |
| MInference (1M token inference) | [MInference: Million-Tokens Prompt Inference for Long-context LLMs — Microsoft Research](https://www.microsoft.com/en-us/research/project/minference-million-tokens-prompt-inference-for-long-context-llms/) | Infrastructure side — sparse attention enables million-token inference. The gateway timeouts we hit are an infrastructure choice, not a model limit. |
| Hierarchical synthetic data for 1M context | [Scaling Instruction-Tuned LLMs to Million-Token Contexts via Hierarchical Synthetic Data Generation](https://arxiv.org/html/2504.12637v1) | Training-side evidence that 1M-context is increasingly viable. |

## D. Specification versioning & evolution

For the spec versioning pattern (intent docs, boundary docs, formal specs).

| Topic | Source | Why it matters to Colosseum |
|---|---|---|
| Schema versioning (database literature) | [Schema Versioning in Databases: A Literature Review — Brahmia (Computing Open Vol 02)](https://www.worldscientific.com/doi/10.1142/S2972370124300024), [companion paper](https://www.worldscientific.com/doi/pdf/10.1142/S2972370124300012) | Comprehensive survey of schema-evolution patterns (eager / lazy / predictive migration). Pattern transfers to intent doc versioning. |
| Schema evolution — formal characterization | [Schema Evolution and Versioning: a Logical and Computational Characterisation — Calvanese et al.](https://www.researchgate.net/publication/221307006_Schema_Evolution_and_Versioning_A_Logical_and_Computational_Characterisation) | Description-Logic formalization of schema changes; reasoning tasks at global + per-version levels. Inspiration for the compose-ledger's version-drift tracking. |
| Service specification evolution | [Managing the Evolution of Service Specifications — Springer LNCS](https://link.springer.com/chapter/10.1007/978-3-540-69534-9_28) | Practical patterns for service-interface evolution. Maps to Colosseum boundary-doc versioning. |
| Spec-driven development (when architecture becomes executable) | [Spec Driven Development: When Architecture Becomes Executable — InfoQ](https://www.infoq.com/articles/spec-driven-development/) | Industry framing of "the spec is the architecture, version-tracked"; aligns with Colosseum's intent-as-first-class artifact stance. |
| Semantic Versioning (SemVer) | [Semantic Versioning for APIs — Zuplo](https://zuplo.com/learning-center/semantic-api-versioning), [Putting the Semantics into Semantic Versioning — Lam (arxiv)](https://arxiv.org/pdf/2008.07069), [Beyond API Compatibility — InfoQ](https://www.infoq.com/articles/breaking-changes-are-broken-semver/) | major.minor.patch convention. Lam's paper notes SemVer's actual semantics often diverge from its theoretical definition — relevant for the methodology's classification of "what counts as a breaking change to an intent doc". |
| Consumer-Driven Contracts | [Consumer-Driven Contracts pattern — enterprise-applications-patterns](https://github.com/lirantal/enterprise-applications-patterns/blob/master/backend/consumer-driven-contracts.md), [How to Implement Consumer Driven Contracts — OneUptime](https://oneuptime.com/blog/post/2026-01-30-consumer-driven-contracts/view) | Consumers define the contract; providers verify they still satisfy it. Maps directly onto Colosseum boundary docs: the downstream component defines what it needs from the upstream component. |

## E. Multi-harness LLM tooling & gateway

Tools the methodology depends on or surfaces failure modes against.

| Tool | Source | Notes |
|---|---|---|
| OpenCode | [opencode.ai docs](https://opencode.ai/docs/agents/), [Providers](https://opencode.ai/docs/providers/), [DeepWiki agent system](https://deepwiki.com/sst/opencode/3.2-agent-system), [Built-in tools](https://deepwiki.com/sst/opencode/5.3-built-in-tools-reference), [Building Agent Teams in OpenCode — DEV community](https://dev.to/uenyioha/porting-claude-codes-agent-teams-to-opencode-4hol), [Local provider setup repo](https://github.com/groxaxo/opencode-local-setup) | Multi-provider terminal agent. Subagents support non-Anthropic models with file-access; Task tool spawns child sessions. The primary dispatch shape relies on this for non-Claude voices. |
| LM Studio | [LM Studio OpenAI Compatibility Endpoints docs](https://lmstudio.ai/docs/developer/openai-compat) | Local OpenAI-format inference server. Verified-rcv dogfood found JIT-load auto-evict contention when used cross-session. |
| Claude Code | [claude.com/claude-code](https://claude.com/claude-code) | Anthropic CLI for the Claude voice (Agent subagent). |
| Custom OpenAI-compatible providers | [OpenCode Custom Provider Setup — haimaker.ai](https://haimaker.ai/blog/opencode-custom-provider-setup/), [Local LLM with OpenCode — tobrun](https://tobrun.github.io/blog/add-openai-compatible-endpoint-to-opencode/) | How to wire LM Studio / vLLM / gateway endpoints into OpenCode. The methodology depends on this pattern for the gateway voice channel. |

## F. Domain references (verified-rcv substrate)

Domain references the verified-rcv intent doc rests on. Not methodology-level, but cited so methodology-level reviewers can independently verify domain claims.

| Topic | Source | Notes |
|---|---|---|
| Instant-Runoff Voting (IRV) | Wikipedia: Instant-runoff voting; Australian federal parliament uses full-preferential batch-elimination | Algorithm semantics for verified-rcv Section 2.5. Spec inherits the Australian federal parliament variant (batch-eliminate lowest tied set, multi-winner fallback). |
| dstack TDX | Phala Network dstack docs | TDX confidential VM substrate. verified-rcv inherits dstack key-manager + attestor primitives from Quartz. |
| zkdcap (Groth16 over TDX quote validity) | Automata Network zkdcap | ZK proof compression for TDX attestation. verified-rcv inherits zkdcap verifier from Quartz. |
| CosmWasm | docs.cosmwasm.com | Smart contract platform. verified-rcv contract uses CosmWasm v2.0 + Borsh serialization. |
| Xion | docs.burnt.com | CosmWasm chain with native ZK module. verified-rcv targets Xion testnet. |
| Quartz | `/Users/mvid/Development/reliq/quartz/` (peer repo) | Cross-project composition target. verified-rcv consumes Quartz's attestation primitives via the boundary documented in Section 6.2. |

## G. Internal artifacts — dogfood evidence base

Produced during the verified-rcv and Quartz dogfood projects. Cited by methodology back-port work.

| Artifact | Path | Role |
|---|---|---|
| Quartz methodology-asks log | `/Users/mvid/Development/reliq/quartz/.colosseum/methodology-v0.2-asks.md` | Original Quartz-side asks driving early methodology revisions. |
| Quartz integration ledger | `/Users/mvid/Development/reliq/quartz/.colosseum/ledger.md` | Axiom classification, theorem-lift index, cross-bundle composition map. Verified-rcv inherits via the Quartz cross-project boundary. |
| Verified-rcv intent doc | `/Users/mvid/Development/reliq/verified-rcv/.colosseum/intent.md` | Greenfield dogfood target. ~728 lines after revision pass against the 7-voice re-adversarial. |
| First-pass adversarial report | `verified-rcv/.colosseum/attacks/intent-first-draft-*.md` | 42 findings (13 critical + 24 serious + 5 cosmetic). Revision-1 was driven by this. |
| Sanity check (interim) | `verified-rcv/.colosseum/attacks/intent-revised-sanity-*.md` | Two-voice interim sanity check between revision-1 and the full re-adversarial. |
| Re-adversarial run dir | `verified-rcv/.colosseum/attacks/intent-revised-*/` | 8 voices dispatched; 7 returned structured reports; goedel errored. `run.json` (manifest), `synthesis.md` (orchestrator output), `synthesis-input.md` (verbatim concat), per-voice files. |
| Gateway bugs report | `verified-rcv/.colosseum/gateway-bugs-*.md` | 4 documented gateway bugs: (1) Gemini route via OpenAI BYOK (resolved); (2) ReadableStream disturbed (resolved); (3) gateway-wide ~240s cap; (4) Anthropic-route Cloudflare 524 at ~127s. |
| Re-adversarial dispatch plan | `verified-rcv/.colosseum/attacks/re-adversarial-dispatch-plan.md` | Lineup design + blindness restrictions for the 6-voice fan-out. |
| Manifest tool | `colosseum/scripts/colosseum_run.py` + `colosseum/scripts/README.md` | Harness-agnostic dispatch coordinator. Verified-rcv was its first dogfood. |
| External-model MCP | `colosseum/mcp/external-model-mcp/` | OpenAI/Google/gateway provider MCP. Extended with the gateway channel during verified-rcv. |

## H. Citation hygiene notes

- Every external link in this register has been seen at time of authoring (per session web-search results). External links can rot; entries record the *title + identifying author / venue* alongside the URL so a future reviewer can re-locate the source if the URL breaks.
- Academic papers (arxiv, ACM, springer): the arXiv / DOI is the canonical identifier; URLs are for convenience.
- Industry / blog references: snapshotted views; treat as "current at time of authoring" unless re-verified.
- Internal artifacts under `colosseum/` or sibling repos: always reachable as long as the repos exist; the methodology repo's `references.md` is the index.

## I. How to add an entry

When a SKILL.md or agent prompt makes an external claim, ensure the source is in this register. New rows: pick the category that fits (or add a new one), include title + author/venue + URL, and a one-line "why it matters to Colosseum". If the source is paywalled or behind a login, note that explicitly so a reviewer knows to seek institutional access.
