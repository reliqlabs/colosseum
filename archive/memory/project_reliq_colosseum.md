---
name: Reliq / Colosseum / verified-cosmwasm project context
description: User is building a formal verification methodology (Colosseum) atop work on verified-cosmwasm and the reliq Quartz library; targeting ranked-choice voting as eventual integration test
type: project
originSessionId: 58c6368a-7b86-40a9-a8cc-b4091a61c61f
---
User is developing three related threads under the reliq umbrella:

1. **reliq quartz library** — application work on Quartz (Informal Systems' TEE-enabled Cosmos framework, used for off-chain enclave compute with on-chain verification)
2. **verified-cosmwasm** — formal verification of the underlying CosmWasm framework. Foundational substrate work; needs to stabilize before higher-level verification efforts can stand on it.
3. **Colosseum** — a methodology (not a product) for building dependable software via mechanized correctness layers: formal verification + adversarial multi-model generation + verification pyramid (types → lints → property tests → fuzz → Kani → Verus → Aeneas/Lean). Located at /Users/mvid/Development/reliq/colosseum. README captures the methodology.

**Why:** User wants to bridge the trust gap between LLM output velocity and human-bottlenecked correctness mechanisms. Thesis: mechanize correctness to match production velocity. Adversarial multi-model generation is treated as superior to consensus.

**How to apply:** When discussing reliq/colosseum/cosmwasm work, understand the layered ambition — verified substrate (cosmwasm) → verified application (eventual Quartz ranked-choice re-implementation) → all built through the Colosseum methodology. First Colosseum run will be a pure ranked-choice tabulation algorithm in Rust (decomposed from the full Quartz example, which is too big for methodology validation). Help anchor scope to "validate the methodology" rather than "ship the flagship example" on early runs.
