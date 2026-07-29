# Calibration run 2026-07-26-r2: kimi-k3 entry test, kimi-k2.6 re-baseline

Second live execution of the M3 recall instrument (`scripts/recall_score.py`,
protocol in `docs/benchmark-protocol.md`). Per-voice calibration, NOT the
pre-registered M3 benchmark: no ablation arms, one target, one pass per voice.

The decision rule was fixed in [`PRE-REGISTRATION.md`](./PRE-REGISTRATION.md)
before any output was read. Read that first; this file reports against it.

## Question

Should `kimi-k3` replace `kimi-k2.6` in `canonical-4`'s Moonshot seat? The
2026-07-13-r1 corpus is burned, so neither voice's existing record could settle
it. Both voices ran on this fresh corpus, so the comparison is like-for-like.

## Design

- Target: `target/` — the `ledger` crate (append-only segmented event log, ~330
  lines, 5 source files), 8 planted defects across 8 root-cause categories.
  Compiles clean under `cargo check`.
- Built harder than 2026-07-13-r1 on that run's own instrument note (it hit a
  ceiling: 3 of 4 voices at 8/8, no discrimination). This corpus plants
  concurrency (D1), cross-file symptom-far-from-cause (D2, D4), and a
  no-op-implementation leak (D7).
- Ground truth `corpus.json`, snapshot-bound to dispatch commit `26231da348a3`.
- Blinding: the corpus never entered the dispatch directory
  (`/tmp/ledger-dispatch`, single commit, worktree clean). Voices saw only the
  crate, `INTENT.md`, and `REVIEW-INSTRUCTIONS.md`.
- Dispatch: one `opencode run` per voice under the deny-first `spec-adversary`
  profile (read-only, no bash/write/network), `--variant max`.
- Match rule (pre-registered, unchanged): file basename + exact category + line
  within tolerance 5. Right-place wrong-category does not count.

## Results

| Voice | Recall | Caught | Missed | Unmatched | Elapsed |
|---|---|---|---|---|---|
| `kimi-k3` | **7/8** | D1, D3, D4, D5, D6, D7, D8 | D2 | 4 | 231s |
| `kimi-k2.6` | **6/8** | D1, D3, D4, D5, D6, D8 | D2, D7 | 6 | 424s |

Union recall: 7/8. Shared blind spot: **D2**.

Both voices produced a parseable findings block; neither errored.

## Decision

Pre-registered rule applied:

- Validity gate — both parseable. Pass.
- Entry floor — K3 needs >= 5/8. K3 scored 7/8. **Pass.**
- Relative bar — K3 must be >= K2.6. 7 >= 6. **Pass.**

**Outcome: swap.** `kimi-k3` enters `canonical-panel` citing this run;
`kimi-k2.6` moves to `candidate`, retaining its 2026-07-13-r1 calibration.

### The margin is one defect, and the decision is robust to it

K3's lead rests entirely on **D7**, and on a category call: both voices found
the `prune_before` no-op, but K3 categorized it `resource-leak` (the corpus
category) while K2.6 called it `invariant-violation` — right place, wrong
category, a miss under the pre-registered rule.

That single judgment does not carry the decision. Under every alternative
scoring of the two contested defects, the pre-registered rule still swaps,
because it accepts parity:

| Scoring | K3 | K2.6 | Rule outcome |
|---|---|---|---|
| As scored | 7 | 6 | swap (K3 ahead) |
| Credit D7 to both | 7 | 7 | swap (parity clause) |
| Credit D2 to both | 8 | 7 | swap (K3 ahead) |
| Credit both to both | 8 | 8 | swap (parity clause) |

So the result is "K3 is at least K2.6's equal on this instrument," not "K3 is
measurably better." The stronger claim is not supported by one defect of
margin. K3 was also 1.8x faster (231s vs 424s), which is an observation, not a
scored criterion.

## Instrument observations

1. **The corpus discriminated.** Unlike 2026-07-13-r1, no voice hit the
   ceiling, and there is a non-empty shared blind spot. The harder axes did
   what the prior run's note asked for.
2. **D2 was found by both and scored against both — for different reasons.**
   This is the pre-registered match rule's cost, paid twice in one run:
   - K2.6 reported `checkpoint.rs:20 invariant-violation` — the **correct
     category**, 6 lines from the planted line 26. Tolerance is 5. Missed by
     one line.
   - K3 reported `checkpoint.rs:26 missing-validation` — the **exact line**,
     wrong category.
   Substantively both saw that `capture()` discards `retention_watermark`. The
   rule stays as pre-registered and this is the recorded example of its cost,
   alongside nemotron's D6 in 2026-07-13-r1. D2 is not mis-specified — it is
   reachable and both voices reached it — so the freeze rule's exclusion clause
   does **not** apply and no re-scoring was done.
3. **Unmatched is not false-positive, again.** Both voices independently
   flagged `segment.rs::prune_before` for retaining a suffix without advancing
   `base_offset`, which breaks `get_relative` indexing. That is a real defect
   the corpus author did not plant. K3 additionally flagged the `.max(1)`
   capacity clamp as an error-swallow at `api.rs:43` — also fair, and adjacent
   to planted D6. Corpus incompleteness is real and the scorer's refusal to
   compute precision without ground-truth labels remains vindicated.
4. **Category attribution is where frontier voices separate now that recall
   ceilings are gone.** Both contested defects turned on taxonomy choice, not
   on detection. A future corpus should either tighten category definitions or
   report a secondary "found, miscategorized" metric.

## What this run does and does not establish

- **DOES**: per-voice recall for `kimi-k3` and `kimi-k2.6` on one fresh seeded
  target under the pre-registered match rule; fitness evidence sufficient for
  K3 to enter `canonical-panel` under the pre-registered floor; a same-
  instrument baseline showing K3 is at least K2.6's equal.
- **DOES NOT**: establish that K3 is measurably better than K2.6 (one defect of
  margin, resting on a category call); any claim about the panel as a whole;
  any claim about either voice against a non-Moonshot seat; precision or
  false-positive rates; the M3 benchmark, which still has not been run.

## Known limitations

- **Authorship is not independent.** The corpus author is the orchestrating
  session — the same second-party weakness recorded for 2026-07-13-r1 and the
  2026-07-14 benchmark. Voices were blind to the corpus; the author was not
  blind to the voices. An independent corpus remains a W2/M6 need.
- One target, one pass per voice, two voices.
- The `ledger` target itself carries at least one unplanted defect (see
  observation 3), so the denominator is a floor on what was findable.

## Corpus burn notice

This corpus is now published and can never be reused for calibration. Future
runs need fresh held-out corpora, per `docs/benchmark-protocol.md`.
