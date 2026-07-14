# Prospective benchmark protocol (M3)

This protocol is pre-registered. No benchmark run has been executed. This
document contains no results. It fixes the design (arms, blinding, metrics,
success and failure predicates) before any data is collected, so a later run
cannot be reverse-fit to a favourable conclusion. When a run is executed, its
outputs are scored by `scripts/recall_score.py` over a seeded-defect corpus
(`templates/seeded-defect-corpus.example.json`) and reported alongside this
document, with negative results published under the same rules as positive
ones.

## Claim under test

Exit criterion 10 of the plan of record: the adversarial multi-voice panel,
with the critique loop, catches more real defects than simpler baselines at a
cost that is worth paying, and an independent team can reproduce the workflow.
The reproduction half is M6 and out of scope here; this protocol measures the
benefit-over-baselines half.

## Ablation arms

Each arm reviews the same targets under the same time and token accounting.
Ordered from cheapest to richest:

1. **Ordinary review** — one pass by a single reviewer with no tool support.
   The floor baseline.
2. **Single model, single pass** — one voice, one shot, no critique.
3. **Repeated same-model** — the same voice sampled N times and unioned
   (self-ensemble). Isolates diversity-from-sampling from diversity-across-families.
4. **Multi-family panel, no critique** — the canonical voices run once each,
   findings unioned, no cross-critique or defense round.
5. **Full adversarial panel** — the multi-family panel plus the C3 critique
   loop (cross-critique, defense, re-cross-critique) under G4 adjudication.

Arms 3 through 5 are the ones that cost real tokens; arm cost is recorded from
`opencode run --format json` token data and reported as cost per confirmed
defect (see `docs/self-measurement.md` for the cost definitions this shares).

## Seeded-defect corpus

Ground truth is a corpus of known planted defects
(`colosseum-seeded-corpus/v1`). Each defect has a `detection_key` of
`file:line:category`. A voice's finding counts as detecting a defect iff:

- the finding's file basename equals the defect's file basename, and
- the finding's category equals the defect's category (case-insensitive,
  trimmed), and
- the finding's line is within the corpus `line_tolerance` of the defect line.

A right-place wrong-category finding does not count as a detection. A finding
that matches no seeded defect is an unmatched detection (a candidate false
positive); it is counted but not converted into a precision number, because
precision requires ground-truth labels on the unmatched set, which this corpus
does not carry.

## Blinding

- Voices never see the corpus. Seeded defects are merged into the target so
  they are indistinguishable from native code; the planted-defect manifest is
  withheld until scoring.
- The adjudicator sees findings with their arm and voice identity stripped, so
  arm 5's findings cannot be favoured over arm 2's on provenance. Identity is
  re-attached only after adjudication, for scoring.

## Metrics

- **Seeded-defect recall per voice and per arm** — matched seeded defects over
  total seeded defects. Computed by `recall_score.py`.
- **Shared blind spot** — seeded defects that no voice in an arm detected. This
  is the direct measure of correlated blind-spot risk: the failure mode a panel
  of correlated models cannot escape. Reported as a set and a rate.
- **Majority-wrong cases** — defects the majority of voices miss, or misjudge
  (mark refuted when real, or confirmed when not). Called out explicitly as the
  headline risk, because they are where a vote-based panel is most confidently
  wrong. Adjudication under G4 closes on evidence, not votes (see the
  adjudication contract), which is the mechanism meant to survive these cases;
  the benchmark measures whether it does.
- **Cost** — tokens per arm and cost per confirmed real defect.

## Success and failure predicates

- **Benefit** holds iff a richer arm's recall exceeds the next-cheaper arm's by
  a margin fixed before the run (default: recall improvement of at least 0.10
  on the seeded corpus), AND the richer arm's shared-blind-spot rate is no
  worse, AND the cost per confirmed real defect is reported so a reader can
  judge whether the margin is worth it.
- **No benefit** is a valid outcome: if arms 4 and 5 do not beat arm 2 by the
  fixed margin, that is reported as no measured benefit, with the numbers.
- **Regression** is reported if a richer arm's shared-blind-spot rate is worse
  than a cheaper arm's (adding voices hid defects rather than surfacing them).

## Negative-results commitment

Results are published whether or not the panel beats the baselines. "No
measured benefit" and "regression" are first-class outcomes and are reported
with the same prominence as a positive result. The word "validated" returns to
the README only after a run shows benefit at reported cost AND an independent
team reproduces it (M6), not before.

## Status

- Recall scorer: ready (`scripts/recall_score.py`, tested by
  `tests/m3_recall.py`).
- Corpus schema: ready (`templates/seeded-defect-corpus.example.json`).
- Benchmark run: **executed 2026-07-14** over a two-target held-out corpus
  (`calibration/2026-07-14-bench1/RESULTS.md`). Headline is a negative
  result, published per this protocol: no arm beat single-voice recall at
  that target scale, and the one concurrency/reentrancy defect was a
  universal blind spot. Caveats recorded there: fork-authored corpus (not
  second-party), two sub-500-line targets, one run per arm, token costs
  unmeasured. A second-party corpus and larger targets remain wanted; this
  run does not retire the protocol.
