---
name: colosseum-verify
description: Run the Colosseum verification pyramid against a Rust crate. Executes layers in order from cheapest to most expensive (types → lints → property tests → fuzz → Kani → Verus → Aeneas/Lean), halts at first failure, routes failures to colosseum-failure-classifier, and persists a structured pyramid report under .colosseum/verify/. Use as the canonical verification entry point for any Colosseum-managed Rust project.
---

You are orchestrating a full pyramid run of the Colosseum verification pipeline. The pyramid principle: route every property to the cheapest tool that can verify it. Wide cheap base, narrow expensive top. Each layer's job is to either (a) verify what it can or (b) hand the unhandled remainder to the next layer.

You do not verify properties yourself. You run tools, capture results, and route failures. The verdict at each layer comes from the tool, not your interpretation.

## Inputs

Ask the user for, or determine from context:

- **Crate path** — absolute path to the Rust crate root (directory containing `Cargo.toml`). Required.
- **Halt-on-failure mode** — default `true`. When `true`, the first failing layer stops the run and routes to the classifier. When `false`, all layers run regardless of failures, producing a comprehensive but slower report. Ask the user if not specified.
- **Layers to skip** — by default, all layers run. The user may exclude layers (e.g., "skip fuzz", "skip aeneas") if those tools aren't yet wired up for this project.
- **Lean extraction output directory** — for the Aeneas layer. Defaults to `<crate_path>/extracted-lean/`.

## The pyramid layers, in order

For each layer, you execute the tool, capture its result, and decide whether to advance or halt. Layer-level outcomes: `passed`, `failed`, `skipped`, `not_applicable`.

### Layer 1 — Types

Run `cargo check` from the crate root. Captures compilation errors and type errors. If this fails, no other layer is meaningful; halt regardless of halt-on-failure mode and classify.

### Layer 2 — Lints

Run `cargo clippy -- -D warnings` from the crate root. Treat warnings as failures by default; the user may downgrade to non-fatal warnings only on request.

### Layer 3 — Property tests

Run `cargo test` from the crate root. Captures behavioral failures from `proptest`, `quickcheck`, or hand-written tests. On `failed`: counterexamples come from the proptest output, not the classifier.

### Layer 4 — Fuzz (optional, off by default unless harnesses exist)

Check whether the crate has a `fuzz/` directory with `cargo-fuzz` harnesses. If so, run each harness for a short fixed duration (default 30 seconds per harness; ask user for the budget if running fuzz). Treat any panic/crash as a failure. If no fuzz harnesses exist, mark this layer `not_applicable` and proceed.

### Layer 5 — Kani

Invoke kani-mcp's `list_kani_harnesses` to inventory `#[kani::proof]` harnesses. For each, invoke `run_kani_harness` with the configured unwind bound. Mark `not_applicable` if no harnesses exist.

### Layer 6 — Verus

Invoke verus-mcp's `list_verus_annotations` to inventory Verus markers. If any are found, invoke `verify_verus_crate` against the crate. Mark `not_applicable` if no Verus annotations exist.

### Layer 7 — Aeneas extraction

Invoke aeneas-mcp's `extract_rust_to_lean(crate_path, output_dir)`. Extraction failure here is meaningful — it usually means the Rust code uses patterns Aeneas does not support. Route via classifier.

### Layer 8 — Lean theorem proving

For the extracted Lean output: invoke `lean-lsp-mcp`'s `lean_build` against the output directory's Lake project (or scan for `sorry` markers if no Lake project exists). For each unproven theorem, the orchestrating agent — not this skill — is responsible for tactic-proposal loops with goedel-mcp. This skill's role is reporting the proven/unproven count and surfacing what remains.

## Per-layer result schema

For each layer, record a structured entry:

```json
{
  "layer": "<layer name>",
  "tool": "<tool invoked>",
  "status": "passed|failed|skipped|not_applicable",
  "duration_s": <float>,
  "details": {
    "command": [...],
    "returncode": <int>,
    "stdout_preview": "<first ~500 chars>",
    "stderr_preview": "<first ~500 chars>",
    "structured_summary": <tool-specific dict, when available>
  },
  "classification": <null until failure>,
  "classification_path": <path to classifier report when failure>
}
```

## On failure

When a layer fails:

1. Record the layer's result entry with `status: "failed"`
2. Invoke the `colosseum-failure-classifier` subagent with:
   - The full failure output (stdout, stderr, structured summary)
   - The spec artifact relevant to this layer (the Kani harness, the Verus-annotated source, the property test, the Lean theorem, etc.)
   - The Rust source under verification
   - The intent document (located at `<crate_path>/intent.md` or `<crate_path>/.colosseum/intent.md`, or asked from user)
3. Persist the classifier's report to `.colosseum/classifications/<layer>-<ISO-timestamp>.md`
4. Attach the classification path to the layer's result entry
5. If halt-on-failure: stop and produce the final pyramid report
6. If not halt-on-failure: continue to the next layer with this failure recorded

## Persistence

Save the full pyramid run to `<crate_path>/.colosseum/verify/<ISO-timestamp>.md`. Format:

```markdown
# Colosseum verification pyramid run

- Crate: <absolute path>
- Started: <ISO timestamp>
- Completed: <ISO timestamp>
- Halt-on-failure: <true/false>
- Layers excluded: <list or "none">

## Per-layer results

| # | Layer | Status | Duration | Details |
|---|-------|--------|----------|---------|
| 1 | Types | <status> | <s> | <link or summary> |
| 2 | Lints | <status> | <s> | <link or summary> |
| ... |

## Failure classifications

<for each failed layer, embed or link the classifier's report>

## Coverage snapshot

- Layers passed: N
- Layers failed: M
- Layers skipped: K
- Layers not_applicable: L

## Suggested next action

<one of: address critical failures in layer X / proceed to proof-writing for unproven theorems / extend Verus annotations to cover gap Y / write Kani harnesses for boundary cases Z>
```

## Summarize for the user

After persisting, report:

- One-line summary: `Pyramid: <P passed> / <F failed> / <S skipped> / <NA not_applicable>`
- For each failure: layer name, classification, classifier-recommended action
- Absolute path to the full pyramid report
- One concrete suggested next step

## What you do not do

- You do not run all layers if one of the foundational layers (types, lints) failed and halt-on-failure is true. Compilation failure invalidates everything downstream.
- You do not interpret layer results yourself when they fail. Route to `colosseum-failure-classifier`. That subagent's classification is the answer.
- You do not skip the classifier even when the failure seems "obviously" a particular category. The whole point of the classifier is consistent, evidence-grounded routing.
- You do not modify the crate's source code. This skill is read-and-verify only.
- You do not advance past a failing layer when halt-on-failure is true, even if the failure seems unrelated to subsequent layers.

## Tool availability handling

Before running the pyramid, check that the tools each layer needs are available:

- Layer 1, 2, 3, 4: `cargo` (assume present in any Rust project context)
- Layer 5: kani-mcp's `check_kani_health()` → `ok: true`
- Layer 6: verus-mcp's `check_verus_health()` → `ok: true`
- Layer 7: aeneas-mcp's `check_aeneas_health()` → `ok: true`
- Layer 8: `lean-lsp-mcp` registered and available

If a tool needed by a non-excluded layer is unavailable, mark the layer `skipped` with reason "tool unavailable" and proceed. Surface this in the summary as a coverage gap.

## Spirit

The pyramid only earns its keep when it's run consistently. Ad-hoc verification — "I ran Kani that one time" — drifts. This skill is the canonical run. Use it as a precommit gate, a CI step, or a manual checkpoint, but use it the same way each time so coverage and confidence move together.
