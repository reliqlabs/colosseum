# Roadmap: status and remaining work

Last updated: 2026-07-13. This is the handoff document. It records where the
2026-07-11 remediation plan of record stands, what remains before the repo may
call itself dependable by its own exit criteria, and who each remaining item
waits on. A new maintainer or session should be able to resume from this file
alone.

## Where things stand

All in-repo phases of the remediation plan are implemented, tested, and
committed on `main`, one commit per item:

| Phase | Items | State |
|---|---|---|
| Phase 0 (containment) | Z1-Z4: deny-first dispatch profiles, worktree + preflight isolation, injection containment, adjudication guard | done |
| P0 (evidence honesty) | E1-E7: Quint/Lean evidence classes, dispatch fail-closed, manifest concurrency, obligation quality, CLI/packaging contracts | done |
| P1 (mechanisms) | C1-C10: two-gate ledger (G1/G2), conformance bridge (G3), critique loop (G4), voice registry, MCP hardening, skill sweep, intent template, baseline floors, dogfood evidence, repository CI | done |
| P2 instruments | M1 coverage dashboard, M2 self-measurement, M3 recall scorer + pre-registered benchmark protocol, M5 boundary skill / system-intent / ledger versioning | done |
| M3 live calibration | `calibration/2026-07-13-r1`: blinded seeded-defect run, six scoreable voices | done |

Gate: `./scripts/ci.py` — frontmatter, agent-lint, roster-drift, doc-links,
dispatch-config, and the full regression suite (`tests/run_all.py`, ~24
suites). Green as of this writing.

The default adversarial panel is pinned as
`canonical-4@sha256:08831d0ce9f2086b` (operator decision 2026-07-13):
`claude-agent` (Fable 5, or the strongest available Opus when Fable is
absent), `gpt-5.6-sol`, `glm-5.2` (Fireworks), `kimi-k2.6`. All four seats
carry cited 8/8 seeded-recall calibration. `registry/voices.json` is the
source of truth; roster docs are generated from it by
`scripts/gen_roster_docs.py`.

## Exit criteria scoreboard

The plan of record's "dependable" gate has ten criteria. Current state:

| # | Criterion | State |
|---|---|---|
| 1 | No control-plane path succeeds with zero valid evidence | satisfied (R1-R6, R20) |
| 2 | Obligations have stable IDs + typed G1 records; manifests frozen | satisfied (R9, R19, R27) |
| 3 | Evidence bound to snapshot/intent/manifest/tools/seeds/hashes | satisfied (R27) |
| 4 | Lean and Quint evidence classes honest | satisfied (R7, R8) |
| 5 | Least-privilege external-model execution + injection fixtures | satisfied (R10-R12; deny-first confirmed live) |
| 6 | Cross-axis claims labeled conformance-tested until refinement exists | satisfied (R24, R26) |
| 7 | Critique loop exercised once on a REAL contested finding, recorded per G4 | open — machinery tested (R23, R25); no real contested-finding record yet |
| 8 | Skills/agents/wrappers pass pinned validators | satisfied (R13) |
| 9 | Known-good reference project passes; known-bad variants fail at intended gates | satisfied (R22, `tests/fixtures/r22/` jobq project + `tests/r22_reference_project.py`) |
| 10 | Prospective benchmark shows benefit at reported cost; independent replication | open (M3 benchmark, M6) |

## Remaining work

### W1. R22 reference project — DONE 2026-07-13

`tests/fixtures/r22/`: the `jobq` crate (single-worker queue, bounded
retries) with INTENT.md, Quint spec, obligations manifest, floors,
hash-bound ledger, and a conformance adapter that path-depends on the real
library. Verified live at authoring time: 6 tests, clippy clean, Apalache
depth-12 on B1-B4, W1 witness trace, 5/5 conformance traces, kani bounded
proof, `VERIFIED[tested]` and `VERIFIED[bounded]`. `tests/r22_reference_project.py`
runs the good project through every gate and six known-bad mutations that
each fail at exactly their intended gate while another stays green. Still
useful as: the W2 benchmark target, the W5 proof target, and the place to
exercise criterion 7's real contested finding (panel attack on the intent
has NOT been run yet; only the mechanical gates have).

### W2. M3 prospective benchmark (owner: maintainer/agent; API cost)

The pre-registered design is `docs/benchmark-protocol.md`; the instrument is
`scripts/recall_score.py`; the worked example is `calibration/2026-07-13-r1`.
Needs, in order:

1. A fresh held-out seeded corpus. The r1 corpus is burned by publication and
   was too easy (three of four scoreable voices ceilinged at 8/8). The next
   corpus must discriminate: cross-file interactions, concurrency, spec-level
   omissions, symptom far from root cause. Multiple targets preferred.
   Stronger design: a second party authors the corpus so the orchestrator is
   also blind (pairs with W4).
2. The five arms run blinded over it: ordinary review, single model, repeated
   same-model, multi-family panel, adversarial panel with critique loop.
3. Results published with negative results and cost accounting, per protocol.

Definition of done: a results file in `calibration/` with all five arms,
including any arm where the panel failed to beat the baseline.

### W3. M4 panel optimization (owner: maintainer/agent; blocked on W2)

No new machinery. Recompose the panel strictly from W2's per-voice
recall/diversity/cost data. Any membership change moves the profile
content-hash; prior panels stay pinnable.

### W4. M6 independent replication (owner: user + external party)

The gate for "validated" returning to the README. Needs:

1. The repo pushed somewhere an external party can reach (main is currently
   local-only).
2. An independent person/team who follows INSTALL.md + QUICKSTART.md on their
   machine (`colosseum_doctor` validates their environment), runs the workflow
   on a target, and returns their evidence trail.
3. Optional but recommended: they author the W2 corpus, closing the
   orchestrator-blindness gap.

The replication protocol exists at `docs/replication-protocol.md` — what to
run, what to return, and how results get recorded
(`replications/<date>-<party>/`, manifest conventions, and the
"validated" gate as a conjunction of a merged replication and published
benchmark results).

### W5. M7 refinement proofs (owner: maintainer/agent; heavy proof work)

For at least one critical relation on a real target (W1's project is the
candidate): Aeneas-extract the Rust to Lean and machine-check that the
extracted model refines the Quint transition relation. Only after such a proof
exists does the `REFINEMENT_VERIFIED` emission path get built; today the label
is emitted nowhere by design (G3, R26). Note the doctor currently reports
Verus not installed; install it first if the Verus layer should participate.

### W6. Housekeeping (owner: user unless noted)

- `gpt-5.6-pro`: blocked by an account-level error at dispatch ("not supported
  when using Codex with a ChatGPT account"). When the account is fixed, one
  dispatch + score calibrates it (agent).
- `deepseek-v4-flash`: requires the local ds4 endpoint (DwarfStar4 at
  `http://127.0.0.1:8000`) to be running; then calibrate on the W2 corpus.
- `gemini-3.1-pro-preview`: requires `GOOGLE_GENERATIVE_AI_API_KEY` (or an
  opencode Google credential); then calibrate on the W2 corpus.
- `colosseum_doctor` checks env vars but not opencode's auth store, so it
  false-warns on voices that authenticate via OAuth (as `gpt-5.6-sol` does).
  Small fix (agent).
- Push `main` (one command once a remote/destination is chosen).

## Suggested sequence

W1 first (unblocks the most: dogfood exemplar, benchmark target, proof target,
criterion 7). Then the W2 corpus and arms, then W3 from its data. W4 runs in
parallel from the moment the repo is pushed. W5 targets W1's critical
invariant opportunistically. W6 items land whenever their inputs appear.

## Provenance

The full remediation plan of record (contracts G1-G5, phases Z/E/C/M, fixtures
R1-R28, exit criteria) came out of a five-round dual-agent adversarial review
closed 2026-07-11. Its narrative lives outside the repo; everything actionable
from it is either implemented (see the scoreboard) or captured above. Fixture
map: `tests/README.md`. Voice evidence: `registry/voices.json` and
`calibration/2026-07-13-r1/README.md`.
