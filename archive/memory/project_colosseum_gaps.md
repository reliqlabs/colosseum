---
name: Colosseum v0.1 gaps surfaced by Quartz dogfooding
description: Methodology gaps in Colosseum v0.1 identified after running Quartz verification work; informs next round of methodology revisions
type: project
originSessionId: 58c6368a-7b86-40a9-a8cc-b4091a61c61f
---
After running real verification work on Quartz (8 Kani harnesses, 2 Quint specs with 20+ invariants, 6 Verus prototypes with 43 verified, 1 Lean spec tree with 16 theorems / 34+ axioms — all 4 CI workflows green locally), the user identified concrete gaps in Colosseum v0.1.

**Why:** These gaps are load-bearing for whether the methodology actually serves real (non-greenfield) verification work. Without addressing them, Colosseum will silently steer users away from its highest-value outputs.

**How to apply:** When extending Colosseum, prioritize gaps in this order:

1. **Cross-component composition is missing.** Per-artifact pyramid layers don't accommodate chained theorems (e.g., enclave commitment + contract discipline + ECIES roundtrip + attestation soundness as a single trust claim). Need `colosseum-compose` skill + integration-ledger artifact. Highest-value proofs span artifacts; current methodology hides them.

2. **Multi-model adversarial is aspirational, not operational.** colosseum-spec-adversary is single-model. README claims diversity. Either wire up Claude+GPT+Gemini routing or downgrade the README claim.

3. **Intent-document skill is greenfield-only.** Most real verification starts from existing code + CLAUDE.md + commits. Need `colosseum-reverse-intent` workflow. User skipped intent doc on Quartz precisely because the template didn't fit.

4. **Pyramid diagram conflates spec-axis with exec-axis.** Quint belongs upstream of code (with Lean math); Kani/Verus belong on real Rust. Workflow step 4 gets this right; the diagram doesn't.

5. **Missing attack category: `temporal_state_mismatch`.** State-only invariant trying to express temporal property. Different from under/over-spec.

6. **Missing failure category: `state_space_blowup`.** Quint/Apalache exhaustion. Distinct from prover_stuck (effort fixes it) and tool_mismatch (Quint is the right tool).

7. **Tracer-bullet discard criteria missing.** Users won't discard working code without explicit gates. Need criteria like: Aeneas can't extract, >2 fundamental restructures needed, interface footprint doubled.

8. **MCP servers all v0.1 untested end-to-end.** Quartz is a near-perfect regression set (working harnesses across all 4 tools). Run kani-mcp's `list_kani_harnesses` against Quartz first; cheapest validation possible.

**Dogfood target:** Quartz itself, not (only) ranked-choice tabulation. Sealed-auction example exercises Quint harder than ranked-choice (no-front-running, deposit handling, winner determinism) — keep both as candidates.
