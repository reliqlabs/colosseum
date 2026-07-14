# Benchmark v2 — DRAFT, not pre-registered

Status: design draft only. v1 (`docs/benchmark-protocol.md`) is executed and
its results published (`calibration/2026-07-14-bench1/RESULTS.md`). This
draft becomes a protocol only when frozen BEFORE any v2 corpus exists, and
the v2 corpus must be authored by a party independent of the orchestrator
(see `docs/replication-protocol.md`, corpus-authorship offer). Until then
nothing here binds anything.

## What v1 established that v2 must respond to

1. Code-review recall on sub-500-line crates saturates: every arm, every
   voice, matched or ceilinged, so the metric cannot discriminate panels
   from single voices there. The one discriminating defect was reentrancy.
2. The panel's demonstrated value showed up in a currency v1 did not
   measure: adversarial spec attack, where individual voices produced
   unique, mutant-proven findings (`dogfood/jobq-2026-07-13/`, F4 and F6
   were single-voice contributions the rest of the panel missed).
3. Cost was unmeasured (token fields null by design); dispatch counts were
   the only proxy.

## v2 design sketch

Two tracks, same arms discipline as v1 (ordinary / single / repeated /
multi-family / adversarial+critique):

- **Track S (spec attack, the new primary).** Targets are intent+spec pairs
  seeded with SPEC-level defects drawn from the jobq adjudication's defect
  catalog: weakened or one-sided invariants, ghost-property omissions
  (monotonicity), constant collapse, missing witnesses, unobservable error
  outcomes, over-pinned parameters. Scoring currency: confirmed unique
  findings per voice after G4-style adjudication, and marginal panel yield
  (findings the single-voice arm did not produce). This measures what the
  panel is actually for.
- **Track C (code recall, re-scoped).** Larger targets (multi-crate
  workspaces, 2k+ lines), defect classes weighted toward what v1 showed
  frontier voices miss: reentrancy and interleaving assumptions, cross-file
  temporal properties, resource lifecycle. Sub-500-line single-crate
  targets are explicitly out of scope; v1 settled those.

Requirements carried into any v2 freeze:

1. Second-party corpus authorship, held out until publication (both tracks).
2. Token accounting mandatory: the dispatch path must capture per-call
   token counts so cost-per-confirmed-finding (M2's metric) is reported
   next to recall/yield; no null-cost publication in v2.
3. At least 3 runs per stochastic arm; report spread, not just point
   estimates (v1's repeated arm was deterministic for one voice; that is
   not established for panels or for Track S).
4. The claude-agent seat participates via an in-harness dispatch shim or is
   excluded BY DESIGN in the frozen protocol, not by tooling accident.
5. Negative results published, as in v1.

## Open questions to settle before freezing

- Track S adjudication cost: G4 adjudication of every arm's findings is
  expensive and partly human; define the adjudicator role (independent
  session, blinded to arm identity) and its budget.
- Whether Track C is worth running at all before a Track S result exists,
  given v1's saturation evidence.
- Corpus size floor for statistical claims (v1's 10 defects support only
  direction-of-effect statements).
