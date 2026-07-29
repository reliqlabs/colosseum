# Pre-registration: calibration run 2026-07-28-r3

**Written before any voice was dispatched.** No model had been asked to review
the target at the time of writing, no output file existed, and nothing had been
scored. This document fixes the decision rule so the result cannot be
reverse-fit. It is committed before dispatch.

## Question under test

Do the four `canonical-4` voices, dispatched over the **OMP-native** transport
at the **deployed** effort and provider routes, demonstrate adversarial fitness
sufficient to fill their `omp_calibration` fields?

Every voice currently carries `omp_calibration: "pending"`. The cited fitness
evidence in each voice's `calibration` field was earned over OpenCode, at
`--variant max`, and for GLM and Kimi over Fireworks. The deployed OMP routes
differ on all three axes, so none of that evidence transfers. Per the registry
rule, a pending OMP route may be exercised experimentally but MUST NOT be called
calibrated. This run is the instrument that settles it.

## Routes under test (frozen)

Route hash `sha256:d501830ac0020cda`. Effort follows the unchanged
`one-below-max` policy: step down one rung from `max`, or take the top rung when
the ladder has no `max`.

| Voice | Selector | Ladder | Why this rung |
|---|---|---|---|
| `claude-agent` | `anthropic/claude-fable-5:xhigh` | low/medium/high/xhigh/max | one below `max` |
| `gpt-5.6-sol` | `openai-codex/gpt-5.6-sol:xhigh` | low/medium/high/xhigh/max | one below `max` |
| `glm-5.2` | `synthetic/hf:zai-org/GLM-5.2:xhigh` | minimal/low/medium/high/xhigh | top rung, no `max` exists |
| `kimi-k3` | `synthetic/hf:moonshotai/Kimi-K3:high` | low/high/max | one below `max` |

GLM and Kimi moved from Fireworks to synthetic on 2026-07-28, an operator cost
decision: synthetic is subscription-priced rather than per-token metered. The
ladder is a property of the provider, so the same policy yields `xhigh` for GLM
on synthetic where it yielded `high` on Fireworks. That is a deliberate,
recorded consequence of moving providers, not a separate effort decision.

## Design

- Target: `target/` — the `leasedb` crate (in-memory lease manager with fencing
  tokens, ~330 lines across 6 source files), authored for this run with 8
  planted defects spanning 8 distinct root-cause categories.
- Domain is deliberately unrelated to both burned corpora (2026-07-13-r1's
  `ttl-cache`/LRU and 2026-07-26-r2's `ledger` segmented log). A lease manager
  shares no structure with either.
- The target compiles clean (`cargo check --all-targets`, no warnings).
- Every planted defect was proven reachable by a scratch test suite before
  freezing. Those tests are NOT shipped in the target: the review instructions
  state that tests are deferred, and a test naming a defect would give it away.
- Difficulty calibration: r1 showed a ceiling effect (3 of 4 voices at 8/8, so
  it did not discriminate) and r2 discriminated (7/8 and 6/8). This corpus is
  built to r2's difficulty. The specific hard shapes planted are SEALED, because
  naming them here would hand a voice reading this file most of the answer key;
  see the commitment below.
- Ground truth: `corpus.json`, schema `colosseum-seeded-corpus/v1`, held out of
  tree for the dispatch window.
- Dispatch: one OMP `agent()` per voice under the deny-first
  `colosseum-spec-adversary` profile (tools restricted to read/grep/glob; no
  bash, no write, no network), via `run_omp_fanout`.
- Match rule (unchanged from `docs/benchmark-protocol.md`): file basename +
  exact category + line within tolerance 5. Right-place wrong-category is a
  miss.
- All four voices review the SAME frozen corpus, so the comparison is
  like-for-like.

## Blinding, and its known limit

The ground truth is held **outside the repository working tree** for the whole
dispatch window (`/tmp/r3-ground-truth/corpus.json`) and is committed only after
detections are frozen. No voice can read this run's answers.

The OMP-native transport, unlike the OpenCode worktree path, does **not** confine
the subagent filesystem; every run stamps `isolation: {"status": "unverified"}`
for exactly this reason. The session-root gate additionally forces
`project_root` to equal the session's cwd, which is this repository. So the
agent-visible tree is the whole Colosseum repo, which contains the two burned
corpora **with their ground truth committed**.

Those files do not contain this corpus's answers, but they do reveal the
author's planting style (8 defects, one per category, favored categories). This
file is itself part of the exposure: an earlier draft named four defects' shapes
and one defect's file, which is why those specifics are now sealed. Two
countermeasures, both pre-registered:

1. The dispatch prompt restricts scope to the target directory and states that
   reading elsewhere in the repository is out of scope.
2. **Post-hoc transcript audit.** Each voice's subagent transcript
   (`history://<agent_id>`) is read after the run. **Any read outside
   `calibration/2026-07-28-r3/target/` marks the voice CONTAMINATED**, and it is
   excluded from the recall denominators. The rule is deliberately that broad
   rather than a list of forbidden files: a list would have to enumerate every
   leak, and this document was itself one. The audit result is published for
   every voice, including the clean ones.

This converts an unenforceable instruction into an auditable one. It is weaker
than filesystem confinement, and that gap is a real limitation of the OMP-native
transport, recorded here rather than papered over. The error direction is safe:
a broad rule can only invalidate a voice, never inflate one.

## Sealed annex commitment

Design details that would reveal defect shapes are held outside the tree for the
dispatch window and published in full with the results. Their content is fixed
now by commitment, so neither can be written or amended after outputs are read:

```
sha256(SEALED-ANNEX.md) = fb5aa2a45d70a1a23020fd103e9bc29ebf0b07e641b4a1e67b6fef6999e4c8d0
sha256(corpus.json)     = 0032b43572f266053d4b8964a9fe48a99600ca4af3c1484531d92ce1656dbea3
```

The annex holds the difficulty-calibration specifics and one location-scoring
rule whose statement would name a defect's file. Both are load-bearing: the
difficulty claim justifies holding r2's floor, and the scoring rule must be
fixed before dispatch to keep scoring mechanical rather than adjudicated. After
publication anyone can verify these hashes against the committed text.

### Amendment, pre-dispatch (recorded, not silent)

The first commit of this file (`fe874c8`) published
`sha256(corpus.json) = d402c732890f5c34b9a8226a9aa1ffa5bdaf2509dcd6a5d6b108044b6e60783c`.
That hash covered the corpus while its `target_snapshot` field still read
`PENDING-FREEZE`, because the field can only be filled once the commit that
freezes the target exists. Setting it to the real freeze commit
(`fe874c8148e7+worktree-clean`) necessarily changed the file's hash, so the
original commitment would no longer verify against the corpus that eventually
gets published. The hash above supersedes it.

Both values are recorded so the substitution is auditable rather than looking
like tampering: replacing `fe874c8148e7+worktree-clean` with `PENDING-FREEZE` in
the published `corpus.json` reproduces the original hash exactly.

This amendment is pre-dispatch. At the time of writing no voice had been asked
to review the corpus and no findings existed. The only model calls made against
the routes under test were two one-line transport probes (`ROUTE-OK`), which is
why the published usage baseline starts at 5 and 1 requests rather than zero.
Nothing in the decision rule, the floor, the match rule, or the corpus content
changed.

### Amendment 2, pre-scoring (recorded, not silent)

The dispatch has run. At the time of writing, what has been observed is: per
voice status, elapsed time, output byte count, the claude-agent error string, and
the usage-ledger deltas. **No findings block has been parsed and nothing has been
scored.** No transcript has been opened. This amendment fixes two rules the
original document left silent on, before any of that happens.

**Retry policy for ERRORED voices.** An ERRORED voice gets exactly ONE retry, as
a fresh stateless dispatch with the identical prompt. Applied uniformly to any
voice in that state, decided before any transcript was read, because a retry
decided after seeing what a dying voice had already found would be
outcome-influenced adjudication.

Both attempts are published. If a voice yields a parseable findings block on more
than one attempt, the FIRST parseable attempt is the one scored: this is a retry
for a broken transport, never a best-of-N sample. If the retry also fails, the
voice is ERRORED and its `omp_calibration` stays `pending`.

**ROUTE-DEGRADED voices are not retried in this run.** A retry would carry the
identical degrade risk, because making the route deterministic means editing
`retry.fallbackChains`, which is shared machine-wide configuration that other
live sessions on this machine depend on for their own failover. Changing it
underneath them to tidy up one calibration is not a trade this run is willing to
make. The voice is recorded as ROUTE-DEGRADED and excluded, and the inability to
pin a route per-dispatch without global side effects is recorded as an instrument
limitation of the OMP-native transport.

Consequence, stated before scoring: at most three of four voices can earn a
non-pending `omp_calibration` from this run, and it may be fewer.

## Route attestation (pre-registered)

The OMP eval bridge does not surface the resolved model, so a voice's own record
cannot prove which provider served it. Verified live before writing this: both
synthetic probes returned `details: None`. `served_by_fallback` therefore cannot
be relied on to detect a silent degrade, and `retry.fallbackChains` maps both
synthetic routes onto Fireworks.

Attestation instead comes from OMP's usage ledger. `omp stats --json` reports
`byModel` with a `provider` field. A baseline snapshot is taken immediately
before dispatch and another immediately after.

**Gate.** If the post-run delta shows any requests attributed to provider
`fireworks` for GLM or Kimi, a fallback fired, and the affected voice measured
a different route than the one under test. That voice is recorded as
ROUTE-DEGRADED and excluded from the recall denominators; its calibration field
stays `pending`. For GLM a degrade changes both provider and rung
(`xhigh` to `high`); for Kimi it changes provider only.

The baseline and post-run snapshots are both published.

## Decision rule (pre-registered)

**Validity gate.** A voice producing no parseable JSON findings block is
ERRORED, not zero-recall, and is excluded from recall denominators (consistent
with `parse_outputs.py`, r1, and r2). ERRORED, CONTAMINATED, and ROUTE-DEGRADED
are all dispatch/validity outcomes, never fitness outcomes.

**Entry floor (absolute).** A voice's OMP route earns a non-pending
`omp_calibration` only if it catches **at least 5 of 8** planted defects under
the match rule. This is r2's floor, held constant deliberately so the two runs
are comparable; the corpus was built to r2's difficulty for the same reason.

**No relative bar.** Unlike r2, this run is not a swap decision between two
candidates for one seat. Each voice is tested against the absolute floor on its
own. A voice scoring below another is not thereby demoted.

**Outcomes, per voice.**

| Condition | Action |
|---|---|
| >= 5/8, route attested, transcript clean | `omp_calibration` cites this run with the score. The OMP-native route becomes calibrated for this voice at this effort and provider. |
| < 5/8, route attested, transcript clean | `omp_calibration` stays `pending`, citing this run as a NEGATIVE result. The voice keeps its `canonical-panel` status, which rests on its OpenCode evidence; the OMP route must continue to be reported as uncalibrated. |
| ERRORED | `omp_calibration` stays `pending`, recorded as a dispatch-path failure, not a fitness failure. |
| ROUTE-DEGRADED | `omp_calibration` stays `pending`. The run measured the fallback pair, and that is recorded as what it is. |
| CONTAMINATED | `omp_calibration` stays `pending`. The score is published but explicitly not used as evidence. |

**Status is not at stake.** `status: canonical-panel` rests on each voice's
OpenCode `calibration` field and is out of scope here. A negative OMP result
narrows what may be claimed about the OMP transport; it does not retire a voice.

**Corpus freeze.** The corpus is frozen at the commit that lands this file. If a
planted defect proves mis-specified or unreachable, it is excluded from the
denominator for ALL voices and the exclusion is recorded with its reason.
Defects are never re-scored per voice.

**Reporting.** Union recall and the shared blind-spot set are reported
regardless of outcome. A negative result is published under the same rules as a
positive one. If every voice clears the floor, the ceiling-effect caveat from r1
is restated: a corpus everyone passes has not discriminated.

## Known limitations

- **Authorship is not independent.** The corpus author is the orchestrating
  session, the same second-party weakness recorded for r1, r2, and the
  2026-07-14 benchmark. Worse here in one specific way: the author (Claude
  Opus 5) shares a model family with the `claude-agent` voice (Claude Fable 5).
  Any author-side blind spot or idiom is most likely to be shared by that seat.
  An independent corpus remains a W2/M6 need.
- **Filesystem is not confined.** See the blinding section. Mitigated by audit,
  not prevented.
- **One target, one pass per voice.** No ablation arms, no repeated sampling, so
  nothing here measures run-to-run variance. This is per-voice, per-route
  fitness evidence for the registry, not the pre-registered M3 benchmark.
- **Four voices, one corpus.** This cannot support a claim about the panel as a
  whole, about deliberation, or about any voice not dispatched.
- **Effort is not isolated.** Each voice runs at exactly one rung. The run
  cannot attribute a result to the rung rather than the model, and in
  particular cannot show what the same voice would score at `max`.
- **Corpus burn.** On publication this corpus is burned and can never be reused
  for calibration, exactly as r1 and r2 were.
