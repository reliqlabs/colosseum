# Pre-registration: calibration run 2026-07-26-r2

**Written before any voice output was read.** Dispatch to both voices was
launched before this file was written; no output file had been opened, parsed,
or scored at the time of writing. This document fixes the decision rule so the
result cannot be reverse-fit.

## Question under test

Should `kimi-k3` replace `kimi-k2.6` in the `canonical-4` profile's Moonshot
seat?

The operator's stated basis is generational supersession (K3 is the current
Moonshot flagship). The registry rule requires cited fitness evidence both to
ENTER `canonical-panel` status and to LEAVE it, and the 2026-07-13-r1 corpus
carries a burn notice, so neither voice's existing record can settle this. This
run is the instrument.

## Design

- Target: `target/` — the `ledger` crate (append-only segmented event log,
  ~330 lines across 5 source files), authored for this run with 8 planted
  defects spanning 8 distinct root-cause categories.
- Deliberately harder than 2026-07-13-r1, per that run's own ceiling-effect
  note (3 of 4 voices scored 8/8 there, so it did not discriminate). This
  corpus plants concurrency (D1), cross-file symptom-far-from-cause (D2, D4),
  and a no-op-implementation leak (D7).
- The target compiles clean (`cargo check`, no warnings). Two decoys were
  deliberately removed before freezing — a second unchecked subtraction in
  `api.rs::read_at` and an unintended `resume_offset` off-by-one — so scoring
  measures planted defects rather than authoring accidents.
- Ground truth: `corpus.json`, schema `colosseum-seeded-corpus/v1`,
  snapshot-bound to dispatch commit `26231da348a3`.
- Blinding: `corpus.json` never enters the dispatch directory
  (`/tmp/ledger-dispatch`, single commit, worktree clean). Voices see only the
  crate, `INTENT.md`, and `REVIEW-INSTRUCTIONS.md` (closed 12-category
  taxonomy, 4 categories with nothing planted, JSON output contract).
- Dispatch: one `opencode run` per voice under the deny-first `spec-adversary`
  agent profile (read-only, no bash/write/network), `--variant max`.
- Match rule (unchanged from `docs/benchmark-protocol.md`): file basename +
  exact category + line within tolerance 5. Right-place wrong-category is a
  miss.
- Both voices run on the SAME corpus, so the comparison is like-for-like.
  `kimi-k2.6` is re-baselined here; its 2026-07-13 8/8 does not transfer.

## Decision rule (pre-registered)

**Validity gate.** A voice producing no parseable JSON findings block is
ERRORED, not zero-recall, and is excluded from recall denominators (consistent
with `parse_outputs.py` and the 2026-07-13-r1 README). If `kimi-k3` errors,
there is no swap.

**Entry floor (absolute).** `kimi-k3` must catch **at least 5 of 8** planted
defects under the match rule. Rationale: the prior corpus's 8/8 bar reflected a
ceiling effect and does not transfer to a deliberately harder corpus; a strict
majority of planted defects, with exact-category attribution, is the bar for
seating a voice on the canonical panel. A voice that misses most planted
defects on a corpus built to target it is not frontier-fit.

**Relative bar.** `kimi-k3` recall must be **>= `kimi-k2.6` recall** on this
same corpus. Strict improvement is not required: at parity the operator's
generational preference decides, which is a roster judgment the registry
already permits among calibrated voices. K3 being *worse* than the incumbent it
displaces blocks the swap regardless of the absolute floor.

**Outcomes.**

| Condition | Action |
|---|---|
| K3 >= 5/8 AND K3 >= K2.6 | Swap. K3 → `canonical-panel` citing this run; K2.6 → `candidate`, its 2026-07-13 calibration retained, demotion recorded as operator supersession with this run as the parity/superiority evidence. |
| K3 >= 5/8 AND K3 < K2.6 | No swap. K3 stays `candidate` with this run cited as its recorded fitness. Report that the operator's frontier-quality premise is not supported by the instrument. |
| K3 < 5/8 | No swap, regardless of K2.6's score. K3 stays `candidate`; this run is cited as a negative result. |
| K3 ERRORED | No swap. Recorded as a dispatch-path failure, not a fitness failure. |

**Incumbent handling.** This run is an entry test for K3 and a same-instrument
baseline for K2.6. It does not by itself demote K2.6: a lower score on a harder
corpus is not grounds to retire a voice holding cited 8/8 evidence. The one
exception is K2.6 scoring 0/8 or ERRORING, which is recorded as a fitness or
dispatch-path failure in its own right.

**Corpus freeze.** The corpus is frozen at `26231da348a3`. If a planted defect
proves mis-specified or unreachable, it is excluded from the denominator for
BOTH voices and the exclusion is recorded with its reason in the results.
Defects are never re-scored per-voice.

**Reporting.** Union recall and the shared blind-spot set are reported
regardless of outcome. A negative result is published under the same rules as a
positive one.

## Known limitations

- **Authorship is not independent.** The corpus author is the orchestrating
  session, the same second-party weakness recorded for 2026-07-13-r1 and for
  the 2026-07-14 benchmark. The voices are blind to the corpus; the author is
  not blind to the voices. An independent corpus remains a W2/M6 need.
- **One target, one pass per voice.** No ablation arms, no repeated sampling.
  This is per-voice fitness evidence for the registry, not the pre-registered
  M3 benchmark.
- **Two voices only.** This run cannot support any claim about the panel as a
  whole, or about either voice relative to a non-Moonshot seat.
- **Corpus burn.** On publication this corpus is burned and can never be reused
  for calibration, exactly as 2026-07-13-r1 was.
