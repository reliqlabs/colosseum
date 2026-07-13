# Calibration run 2026-07-13-r1: seeded-defect recall per voice

First live execution of the M3 recall instrument (`scripts/recall_score.py`,
protocol in `docs/benchmark-protocol.md`). This is a per-voice calibration
run, NOT the pre-registered benchmark: no ablation arms, one target, one
pass per voice. Its purpose is fitness evidence for the voice registry.

## Design

- Target: `target/` — the `throttle` crate (token-bucket + sliding-window
  rate limiter, ~250 lines), authored for this run with 8 planted defects
  spanning 8 distinct root-cause categories and 4 files. Ground truth in
  `corpus.json` (schema `colosseum-seeded-corpus/v1`), snapshot-bound to
  the dispatch commit `c6429a67e0ff`.
- Blinding: the corpus never entered the dispatch directory. Voices saw
  only the crate, `INTENT.md` (contract B1-B8), and `REVIEW-INSTRUCTIONS.md`
  (closed 12-category taxonomy, 4 unplanted distractor categories, JSON
  output contract). The claude-agent voice ran as a fresh context-free
  subagent, not a fork of the orchestrating session.
- Dispatch: one `opencode run` per gateway voice under the deny-first
  `spec-adversary` agent profile (read-only, no bash/write/network), from a
  clean single-commit git repo. claude-agent in-harness, read-only.
- Match rule (pre-registered): file basename + exact category + line within
  tolerance 5. Right-place wrong-category does not count.
- Scoring: `outputs/*.md` → `parse_outputs.py` → `detections.json` →
  `recall_score.py` → `recall.json`.

## Results

| Voice | Recall | Caught | Unmatched extras | Notes |
|---|---|---|---|---|
| claude-agent | 8/8 | D1-D8 | 1 | extra is a real unplanted defect (see below) |
| gpt-oss-120b | 8/8 | D1-D8 | 0 | clean contract-following, exact lines |
| kimi-k2.6 | 8/8 | D1-D8 | 0 | |
| glm-5.2-fireworks | 8/8 | D1-D8 | 0 | same-day addendum; Fireworks route after the burnt-gateway route failed |
| gpt-5.6-sol-pro | 8/8 | D1-D8 | 3 | same-day addendum; extras are marginal arithmetic calls on counters |
| gpt-5.6-sol | 8/8 | D1-D8 | 2 | same-day addendum; calibrated after the operator standardized on the sol variant as the OpenAI seat |
| nemotron-3-120b-a12b | 7/8 | all but D6 | 2 | found D6's line but labeled it `missing-validation`, not `error-swallowed`; a right-place wrong-category miss under the pre-registered rule |
| glm-5.2 (burnt route) | errored | n/a | n/a | gateway "Unexpected server error" on both attempts; excluded from recall denominators, not scored as zero |

Union recall: 8/8. Shared-blind-spot set: empty.

### Same-day addendum (glm-5.2-fireworks, gpt-5.6-sol-pro)

Two voices were added hours after the initial dispatch, same corpus, same
protocol, same blinding. Validity: the corpus had been committed locally
but never pushed anywhere, so neither API model could have seen it; the
burn notice below applies from publication onward. glm-5.2 ran via
`fireworks-ai/accounts/fireworks/models/glm-5p2` after the burnt-gateway
route proved dead (the gateway config never exposed glm-5.2, only
glm-4.7-flash). `openai/gpt-5.6-pro` was also requested but the account
rejects it at dispatch time ("not supported when using Codex with a
ChatGPT account", an account-level issue, retry pending); the
registry-pinned `gpt-5.6-sol-pro` variant worked over the same credential
and was calibrated instead.

## Instrument observations

1. **Ceiling effect.** Three of four scoreable voices hit 8/8. This corpus
   does not discriminate among frontier voices; the only separation came
   from the exact-category rule. The next corpus needs harder defects:
   cross-file interactions, concurrency, spec-level omissions, and defects
   whose symptom is far from their root cause.
2. **The category rule does real work.** Nemotron's D6 miss is exactly the
   right-place-wrong-category case the protocol pre-registered as a miss.
   Whether `unwrap_or` on a config parse is "error-swallowed" (symptom) or
   "missing-validation" (adjacent framing) is a defensible disagreement;
   the rule stays as pre-registered, and this case is the recorded example
   of its cost.
3. **Unmatched is not false-positive.** claude-agent's unmatched extra
   (`src/api.rs:48`, unbounded per-key HashMap growth) is a genuine defect
   the corpus author did not plant. Corpus incompleteness is real; the
   scorer's refusal to compute precision without ground-truth labels is
   vindicated.
4. **glm-5.2 gateway instability.** Trivial one-line probes partially
   respond; agentic runs fail server-side ("Unexpected server error",
   refs err_f8ee989f, err_1de17803). Recorded in the registry notes.

## What this run does and does not establish

- DOES: per-voice recall on one seeded target under the pre-registered
  match rule; contract-following fitness for gpt-oss-120b, kimi-k2.6,
  nemotron, glm-5.2 (Fireworks route), and gpt-5.6-sol-pro; dispatch-path
  failure evidence for glm-5.2's burnt-gateway route and for
  gpt-5.6-pro on the current account.
- DOES NOT: the blinded benchmark with ablation arms (still not run); any
  cross-voice superiority claim (ceiling effect); precision or
  false-positive rates; panel-composition decisions (M4 needs a harder,
  multi-target corpus first).

## Corpus burn notice

This corpus is now published and can never be reused for calibration.
Future runs need fresh held-out corpora, per `docs/benchmark-protocol.md`.
