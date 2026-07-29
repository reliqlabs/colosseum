# Calibration run 2026-07-28-r3: OMP-native routes

First calibration of the **OMP-native** transport. Decision rule fixed in
`PRE-REGISTRATION.md` and committed before dispatch (`fe874c8`); the ground truth
and the design annex were held outside the tree and committed only by sha256,
both of which verify against the published files.

## Headline

**One of four voices earned a calibrated OMP route, and the corpus mostly failed
to discriminate.** All four cleared the pre-registered recall floor comfortably.
Recall was never the binding constraint: three voices failed the
route-attestation gate, one because it demonstrably degraded to a different
provider mid-run and two because the instrument cannot prove which provider
served them.

The run's most useful outputs are negative: a precise account of why three routes
cannot be cited, and two instrument defects that would have produced a published
falsehood if they had gone unnoticed.

## Results

Denominator is **7**, not 8: D1 was excluded for all voices as mis-specified,
under the pre-registered corpus-freeze clause. See "The D1 exclusion" below; it
is the most consequential finding in this run.

| Voice | Selector | Recall | Missed | Route grade | `omp_calibration` |
|---|---|---|---|---|---|
| `kimi-k3` | `synthetic/hf:moonshotai/Kimi-K3:high` | 6/7 (86%) | D8 | **ATTESTED** | **cited** |
| `claude-agent` | `anthropic/claude-fable-5:xhigh` | 7/7 (100%) | none | UNATTESTED | stays pending |
| `gpt-5.6-sol` | `openai-codex/gpt-5.6-sol:xhigh` | 7/7 (100%) | none | UNATTESTED | stays pending |
| `glm-5.2` | `synthetic/hf:zai-org/GLM-5.2:xhigh` | 6/7 (86%) | D6 | **DEGRADED** | stays pending |

Union recall 7/7. **No shared blind spot.** Every planted defect was found by at
least three voices, and five of seven by all four.

Transcript audit: **all four clean.** Every voice's tool calls (12, 12, 13 and 31)
stayed inside `target/`; none read another corpus, the pre-registration, or
anything else in the repository.

The raw mechanical output over all 8 defects is preserved unmodified in
`recall.json`; `recall-adjusted.json` applies the exclusion. `corpus.json` was
never edited and still matches its pre-dispatch sha256.

## The D1 exclusion, and the blind spot that does not exist

The first scoring pass reported that D1, the concurrency defect, was caught by
exactly one voice, and that concurrency was a universal blind spot among the
others. **That conclusion was false, and it was an artifact of the corpus.**

All four voices found the planted TOCTOU and described it correctly: `acquire`
checks liveness under a read lock, releases it, then inserts under a separate
write lock, so two concurrent acquirers both get a grant. Every one of them
anchored that finding at the insert site (68, 68, 68, 69) rather than at the
liveness read the ground truth named (52), which is outside the tolerance-5
window.

Worse, the single in-window hit that scored as a match was not the planted
defect at all. `glm-5.2`'s finding at `api.rs:48` describes the **capacity**
check race ("admitting leases beyond max_leases") -- a real, unplanted defect of
the same category in the same file, which all four voices also found. So the
window simultaneously denied credit to three voices for a defect they did report
and granted it to a fourth for one it did not.

D1 is therefore mis-specified on two independent counts:

1. **Ambiguous fix site.** The check-then-act window spans lines 52 to 68. Both
   ends are legitimately "the line a fix would change": hold the write lock from
   the start, or move the check under it. The instructions do not pick one, and
   the ground truth silently did.
2. **A competing real defect inside the tolerance window.** The unplanted
   capacity race at 46-48 is indistinguishable from D1 under a rule that keys on
   file, category and line proximity alone.

The pre-registration's corpus-freeze clause covers exactly this: a mis-specified
defect is excluded from the denominator for ALL voices, with the reason recorded,
and never re-scored per voice. Applied uniformly, which also strips `glm-5.2`'s
false credit.

This is the third time concurrency has come up in this project's calibration
history, and it now cuts the other way. The 2026-07-14 benchmark's reentrancy
defect (BD5) was missed by all 28 dispatches; r2 planted concurrency as its
hardest shape. Here every voice found it, and only the instrument failed.

**Consequence for the corpus schema:** a single anchor line plus a symmetric
tolerance cannot express a defect whose fix site is a multi-line window, and it
cannot exclude a same-category neighbour. Future corpora need either a line range
or an explicit anchor rule per defect, and a pre-dispatch sweep for unplanted
same-category defects inside every tolerance window. Both are cheap; neither was
done here.

## What the corpus failed to do

With D1 excluded, two voices scored 100% and two scored 86%. That is r1's ceiling
effect returning: the corpus barely discriminated, and the one defect that
separated the field was the mis-specified one. The sealed annex claimed this
corpus was built to r2's difficulty; on the evidence that claim did not hold, and
the difficulty argument for holding r2's 5/8 floor is weaker than it looked.

Every voice cleared the floor by a wide margin, so no outcome turns on how the
floor scales from a denominator of 8 to 7. Stated for completeness: all four
cleared it on the absolute count of 5 as written.

The genuine misses are narrow and both are anchor-discipline failures rather than
comprehension failures. `kimi-k3` missed D8 by filing the waiter leak at
`register_waiter` (118) instead of the `release` site a fix would change (101),
where the other three correctly put it; the instructions are explicit on this
point, so it is a real miss. `glm-5.2` missed D6 by filing the zero-ttl coercion
in `renew` (90) rather than the planted one in `acquire` (49) -- and `renew` does
contain an equivalent unplanted coercion, so it found a real defect and missed
the scored one.

Everything else was found by nearly everyone: D2, D3, D4, D5 and D7 were caught
by all four, D8 by three, D6 by three.

## Why three routes are not attested

The OMP eval bridge does not surface the resolved model, verified before dispatch
and recorded in the pre-registration: both probes returned `details: None`, and
`served_by_fallback` was empty for this entire run even though a fallback
provably fired. Attestation therefore came from OMP's usage ledger
(`omp stats --json`, which carries a `provider` field).

**`glm-5.2` degraded.** `fireworks|glm-5.2` went from absent to 22 requests while
`synthetic|hf:zai-org/GLM-5.2` took 10. The hourly buckets place the synthetic
traffic at 11:00 and the fireworks traffic at 12:00, and GLM's dispatch ran
11:53 to 12:24, crossing that boundary. It also took 1827s against 254-418s for
the others. Synthetic served the start, then OMP's retry layer moved it to
Fireworks, which changes **both** provider and rung: the configured chain pins
`fireworks/glm-5.2:high`, one rung below the `xhigh` under test. Excluded per the
pre-registered gate.

**`claude-agent` and `gpt-5.6-sol` cannot be attested either way.** The ledger
detects a degrade only when the fallback target has no existing counter, so a new
entry has to appear. Their configured first hops are already-active routes:

| Voice | First fallback hop | Already active? |
|---|---|---|
| `claude-agent` | `openai-codex/gpt-5.6-sol:xhigh` | yes |
| `gpt-5.6-sol` | `synthetic/hf:moonshotai/Kimi-K3:high` | yes |
| `kimi-k3` | `fireworks/kimi-k3:high` | **no** |

A partial degrade onto an already-active counter is invisible, which is exactly
the shape `glm-5.2` exhibited. `kimi-k3` is attested precisely because its only
hop was inactive and stayed absent.

Corroboration, not attestation: pairwise findings overlap is 0.50 to 0.56 among
the three non-degraded voices, so no two collapsed onto one model, and
`anthropic|claude-fable-5` grew by 34 requests inside the window. Both are
consistent with clean routes. Neither proves one, so neither is treated as
evidence.

The ledger also proved non-monotonic across the window: two providers showed
negative deltas between the baseline and post-run snapshots, though two
back-to-back reads were stable. So absence of growth cannot be used as proof
either.

**The fix, for the next run:** clear `retry.fallbackChains` for the routes under
test so a degrade is impossible by configuration rather than merely detectable.
This run deliberately did not do that, because those chains are machine-wide and
other live sessions depend on them for their own failover; that reasoning is
recorded in Amendment 2, before any output was parsed.

## Instrument defects found

**1. Raw evidence was wrapped in a transport envelope.** Three voices' outputs
landed on disk as `{"findings_json": "```json\n[...]```"}` rather than their own
text, because `omp_fanout._result_text` serializes a subagent that yields
structured output. All three emitted a fully compliant fenced JSON array. The
first parse therefore reported them as ERRORED, which would have recorded three
false zero-recall results.

The parser now unwraps any JSON envelope before searching for the fence,
uniformly for every voice. This is a fix to the measuring instrument, applied
identically to all four, not a per-voice adjudication. `omp_fanout` is also fixed
at source: `_result_text` now unwraps a single-string structured payload, so
future raw evidence is the voice's own text. A payload with two or more fields is
still preserved whole, because there is no basis for choosing between them and
guessing would silently drop evidence.

**2. `glm-5.2` cited line numbers systematically one higher** than the file on
disk (api.rs:86 for :85, reaper.rs:28 for :27). Every one still matched inside
the tolerance-5 window, so it cost nothing here, but a corpus with a tighter
tolerance would have scored it as a total miss for a purely presentational
offset.

## Retries

`claude-agent` failed on attempt 1 (`RuntimeError: agent() subagent
'colosseum-spec-adversary' failed.`, 65 bytes, 309s) and succeeded on attempt 2
(7870 bytes, 389s). The retry rule was fixed in Amendment 2 **before** any
transcript was opened or any finding parsed, precisely so that retrying a dying
voice could not be an outcome-influenced choice. Both attempts are published:
`outputs/claude-agent.attempt1.err` and `outputs/claude-agent.md`. The rule scores
the first parseable attempt, so this is a transport retry and never a best-of-N
sample.

## What this run does and does not license

**Licensed.** `kimi-k3`'s OMP-native route at
`synthetic/hf:moonshotai/Kimi-K3:high` may be described as calibrated, citing
6/7 on this corpus, D1 excluded. That is one voice, one pass, one corpus.

**Not licensed.** Nothing about the panel as a whole, about deliberation, about
run-to-run variance, or about any voice at any other rung. Three of four
OMP-native routes remain uncalibrated and must continue to be reported that way.
The `canonical-panel` status of all four voices is untouched: it rests on their
OpenCode evidence and was never at stake here.

**Explicitly not licensed:** any claim that the effort reduction is free. Every
voice ran one rung below its ladder's top (or at the top where no `max` exists),
and no voice ran at `max` on this corpus, so the run cannot attribute any result
to the rung rather than to the model.

## Files

| File | What it is |
|---|---|
| `PRE-REGISTRATION.md` | decision rule, frozen before dispatch, with two recorded amendments |
| `SEALED-ANNEX.md` | difficulty specifics + the D7 location rule, held out of tree during the run |
| `corpus.json` | ground truth, 8 defects, held out of tree during the run |
| `target/` | the frozen `leasedb` crate the voices reviewed |
| `outputs/` | each voice's raw output, plus attempt 1's error |
| `detections.json` / `errored.json` | parsed findings per voice |
| `recall.json` | scored recall, per voice and union |
| `route-attestation.json` | usage-ledger baseline, post-run snapshot, and deltas |
| `stats-baseline.json` | pre-dispatch usage snapshot |
| `parse_outputs.py` | extractor, extended to unwrap the transport envelope |

## Corpus burn

On publication this corpus is burned and can never be reused for calibration,
exactly as 2026-07-13-r1 and 2026-07-26-r2 were. A fourth run needs a fourth
corpus, and it still needs an author who is not the orchestrating session.
