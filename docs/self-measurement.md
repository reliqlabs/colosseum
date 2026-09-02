# Self-measurement (M2)

How FV measures its own adversarial process. These are metrics the
system computes about itself from run artifacts. They are not evidence that
the process helps: a system measuring itself cannot establish external
benefit. External benefit is the job of the blinded benchmark (M3) and
independent replication (M6). Read this document as "what the numbers mean"
before reading any number `self_measure.py` prints.

Every metric here is computed only over data actually present in the run
artifacts. When the input needed for a metric is absent, `self_measure.py`
reports the metric as INCOMPLETE and exits 3. It never substitutes a default
or a zero for missing data.

## Inputs

- **Findings JSON** (adversarial run output): an object with `confirmed`,
  `refuted`, `judgments`, and `dimensionSummaries` lists. Each finding
  carries `severity`, `sources` (the voices or dimensions that raised it),
  and, for confirmed/refuted, a `verdict.confirmed` boolean set at
  adjudication.
- **Run manifest** (`.fv/attacks/<run_id>/run.json`, written by
  `fv_run.py`): carries `run_id`, `phase` (the round: `attack`,
  `critique`, ...), and the `voices` panel.
- **Event data** (OMP structured agent status and handle metadata): per-voice
  token counts when the dispatch preserved them.

## Metric 1 — Adversarial yield

Per voice, per round: how many findings a voice raised, bucketed by
severity, and how many of them survived adjudication.

- A finding is **attributable** to voice V iff V appears in the finding's
  `sources` list.
- A finding raised by k voices (`len(sources) == k`) counts as **1/k** to
  each of its sources. Fractional attribution keeps the per-voice totals
  summing to the finding count; a finding is not double-counted as a full
  find for every voice that happened to also raise it. Whole-finding counts
  are reported separately as `raised_any` so both views are available.
- **Confirmed** vs **refuted** is read from `verdict.confirmed` at
  adjudication (G4). Yield for a voice = confirmed attribution / total
  attribution. A voice that raises many findings that all get refuted has
  low yield; this is the signal that separates noise from signal.

Yield measures a voice's contribution to the confirmed set. It does not
measure correctness of the adjudication itself, and it is not a per-voice
"skill" score across runs (that is calibration, M3, which needs a labeled
seeded-defect corpus).

## Metric 2 — Cost

Per voice: token cost pulled from the event data, and cost per confirmed
finding (voice token total / voice confirmed attribution).

When the run did not preserve token data, cost is reported as the string
`"unmeasured"`. It is never reported as 0. A missing measurement and a
measured zero are different facts and the surface keeps them different.

## Metric 3 — Cheapest-capable-layer routing

This is the metric behind the pyramid's central claim: that routing a defect
to the cheapest tool that can catch it is cheaper than reaching for the
heavy prover first. The claim is only meaningful against a number, so the
number is defined here before it is ever printed.

Order the verification layers by cost, cheapest first:

    types < lints < property-tests < fuzz < kani < verus < aeneas-lean

For a given defect:

- its **cheapest-capable layer** is the cheapest layer in that order whose
  method could in principle witness the defect's class (e.g. a type error is
  capable-at `types`; a rare-state invariant violation is capable-at `kani`
  or a model checker, not at `types`);
- its **actual-catching layer** is the layer that first caught it in the run.

The **routing metric** is the fraction of defects whose actual-catching
layer is at or below (no more expensive than) their cheapest-capable layer:

    routing = |{ d : rank(actual(d)) <= rank(cheapest(d)) }| / |defects|

A defect that a cheap layer *should* have caught but only an expensive layer
did (`rank(actual) > rank(cheapest)`) counts against the metric: it is a
routing miss, evidence that the cheap layer's coverage has a hole. This is
the failure mode the metric exists to expose. Reaching the prover for
something types would have caught is waste; the metric names the waste.

"Capable" is a claim about a defect class, not a guess. `self_measure.py`
does not infer it. Capability and actual-catching layer are supplied per
defect in a **layer-map** (declared in a seeded-defect corpus, M3, or hand-
labeled for a specific run). Over an unlabeled field run there is no honest
way to assign cheapest-capable layer, so `self_measure routing` without a
layer-map exits 3 INCOMPLETE and says so. It does not estimate the fraction.

## What these metrics are not

They are self-observation. A high yield or a favorable routing fraction on
one run says the process behaved a certain way on that run, over a corpus
the process itself surfaced. It does not say the panel beats a cheaper
baseline, does not measure shared blind spots (M3's seeded-defect recall
does that directly), and does not license the word "validated" anywhere.
That word returns only after M6.
