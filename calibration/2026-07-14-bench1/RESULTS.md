# Benchmark run 2026-07-14-bench1: five pre-registered arms, two targets

First execution of the blinded ablation benchmark pre-registered in
`docs/benchmark-protocol.md`, run with `scripts/benchmark_run.py` (one
dispatch abstraction, corpus never visible to any prompt). The headline is
a negative result and is published as such, per protocol.

## Design

- Corpus: `corpus/` — two purpose-built crates (alpha: TTL+generation LRU
  cache; beta: chunked wire-protocol framer), 5 seeded defects each, all
  four hardness axes (cross-file, concurrency/reentrancy,
  symptom-far-from-cause, spec-level omission), plus non-corpus distractors.
  Authored by a fork of the orchestrating session and held out of the repo
  until this publication; voices were blind, authorship was NOT independent
  (the protocol's stronger second-party design remains wanted). The corpus
  is now burned.
- Panel: `openai/gpt-5.6-sol` (also the single/repeated/ordinary-arm
  voice), `fireworks-ai/.../glm-5p2`, `burnt/.../kimi-k2.6`. The
  claude-agent seat cannot ride the opencode dispatch template and was not
  in any arm (limitation).
- Arms per target: ordinary (neutral framing) 1 dispatch; single
  (adversarial instructions) 1; repeated same-model 3; multi-family 3;
  adversarial (multi-family + one authorship-blinded critique round) 6.
  28 dispatches total. Match rule as pre-registered: basename + exact
  category + line tolerance 5.

## Recall

| Arm | alpha (5 defects) | beta (5 defects) |
|---|---|---|
| ordinary | INCOMPLETE (no parseable findings block) | 0.8 |
| single | 1.0 | 0.8 |
| repeated (3 passes) | 1.0 / 1.0 / 1.0 (union 1.0) | 0.8 / 0.8 / 0.8 (union 0.8) |
| multi-family (union) | 1.0 | 0.8 |
| adversarial round 1 (union) | 1.0 | 0.8 |
| adversarial round 2 (union) | 1.0 | 0.8 |

Per-voice on beta: gpt-5.6-sol 0.8, glm-5.2 0.8, kimi-k2.6 0.6. Unmatched
detections (candidate false positives) ran 1-8 per voice per arm; no
precision number is computed, per the scorer's rule.

## Findings

1. **No measurable multi-voice recall benefit at this target scale.** On
   beta every arm scored the same 0.8 union: the three-voice panel, the
   critique round, and three repeated passes all matched one single-voice
   pass. On alpha everything that ran scored 1.0. The panel bought zero
   additional recall on this corpus while costing 3-6x the dispatches.
   This is the negative result the protocol committed to publishing.
2. **BD5 is a universal blind spot.** The corpus's one
   concurrency/reentrancy defect (beta `parse.rs:59`: a byte budget
   snapshotted before a delivery loop goes stale when the intent's K2
   explicitly permits reentrant feeding from the handler callback) was
   caught by no voice in no arm across all 28 dispatches, and no detection
   landed within tolerance of its line under ANY category, so this is a
   true reasoning gap, not a labeling artifact. Reentrant-control-flow
   reasoning is the axis that discriminates frontier voices from the
   corpus author; future corpora should weight it heavily.
3. **Repeated same-model passes are near-deterministic.** Three
   independent gpt-5.6-sol passes caught identical defect sets on both
   targets. Self-ensembling bought nothing here.
4. **Adversarial framing mattered once, for contract-following, not
   recall.** The neutral ordinary arm equalled the adversarial arms on
   beta (0.8) but failed the output contract entirely on alpha (no
   parseable findings block; recorded INCOMPLETE, not zero).
5. **Saturation persists.** Alpha, despite cross-file and
   symptom-far-from-cause defects, ceilinged at 1.0 for every voice,
   confirming the r1 lesson at higher authored difficulty: recall on
   sub-500-line crates does not discriminate frontier models except on
   reentrancy.

## Cost accounting

Token counts are null throughout (`summary.json`): the default dispatch
path emits no token data, and numbers are not invented. Proxy: dispatch
counts above (the panel arms cost 3x and 6x the single arm's dispatches
for equal recall); wall-clock per dispatch ranged roughly 1-10 minutes
with kimi-k2.6 the slowest seat. One kimi dispatch errored transiently
(alpha multi-family) and was excluded from denominators, not zeroed.

## Instrument notes

Two real runner bugs surfaced on first live contact and are fixed in-repo:
voice ids with path separators broke raw-artifact filenames, and opencode
resolves its project from `$PWD` so the dispatcher must pin PWD to the
dispatch cwd. The stub-based suite could not have caught either; live runs
are part of the test surface now.

## What this run does not establish

- Any claim about targets beyond two sub-500-line Rust crates.
- Precision/false-positive rates (unmatched counts recorded, unlabeled).
- Anything about the claude-agent seat (not in the arms).
- Independence of corpus authorship (fork-authored; second-party corpus
  still wanted, ties to M6 replication).
- Statistical confidence: one run per arm; the repeated arm's determinism
  suggests low run-to-run variance for same-voice arms, but panel-arm
  variance is unmeasured.
