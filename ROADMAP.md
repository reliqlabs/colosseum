# Roadmap: status and remaining work

Last updated: 2026-07-19. This is the handoff document. It records where the
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
dispatch-config, fixture-tracking, and the full regression suite
(`tests/run_all.py`, ~24 suites). Green locally as of this writing. The
GitHub Actions mirror (`colosseum-ci` on `main`) is green since 2026-07-14;
on its toolchain-less runner the toolchain-dependent suites degrade to a
tolerated INCOMPLETE rather than failing (see the CI section below).

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
| 7 | Critique loop exercised once on a REAL contested finding, recorded per G4 | satisfied (`dogfood/jobq-2026-07-13/ADJUDICATION.md`: panel attack on jobq; F2 finite-arithmetic gap retained OPEN under G4, corroborated by the W5 Aeneas proof) |
| 8 | Skills/agents/wrappers pass pinned validators | satisfied (R13) |
| 9 | Known-good reference project passes; known-bad variants fail at intended gates | satisfied (R22, `tests/fixtures/r22/` jobq project + `tests/r22_reference_project.py`) |
| 10 | Prospective benchmark shows benefit at reported cost; independent replication | half-open — the benchmark RAN 2026-07-14 (`calibration/2026-07-14-bench1/RESULTS.md`) and the published result is NEGATIVE: no arm beat single-voice recall on the two-crate corpus, so the "shows benefit" clause is currently unmet on the evidence; independent replication still needed |

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

DONE 2026-07-14: all five arms ran over the held-out two-crate corpus and
the results are published at `calibration/2026-07-14-bench1/RESULTS.md`,
definition-of-done met including its hardest clause: the published headline
is the arm where the panel failed to beat the baseline (every arm scored
0.8 union on beta and 1.0 on alpha; the panel bought zero recall at 3-6x
dispatch cost; the one reentrancy defect was a universal blind spot).
Remaining for a stronger W2 iteration, not blockers: a second-party
corpus (pairs with W4), larger targets, reentrancy-weighted defect
classes, and a token-accounting dispatch path.

### W3. M4 panel optimization (owner: maintainer/agent; blocked on W2)

No new machinery. Recompose the panel strictly from W2's per-voice
recall/diversity/cost data. Any membership change moves the profile
content-hash; prior panels stay pinnable.

### W4. M6 independent replication (owner: user + external party)

The gate for "validated" returning to the README. Needs:

1. DONE 2026-07-14: `main` is pushed to github.com:reliqlabs/colosseum and
   CI is green there, so a replicator's fresh clone matches what local CI
   gates (two broken-clone bugs found and fixed on the way; see the CI
   section).
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

### W5. M7 refinement proofs — refinement PROVED 2026-07-14; emission gated

Feasibility spike DONE 2026-07-13, refinement proof DONE 2026-07-14
(`docs/m7-feasibility.md` narrative, `spikes/2026-07-13-m7-aeneas/` Lean
source + repro; heavy build outputs held outside the repo, paths in the
`m7-aeneas-toolchain` memory). jobq extracts to Lean with zero crate
changes (Charon + Aeneas) and `JobqRefinement.lean` now PROVES the
extracted model refines the strengthened Quint transition relation,
forward direction, at CAPACITY=2: 18 theorems, sorry-free, standard axioms
only (`[propext, Classical.choice, Quot.sound]`, independently
re-verified). The five spec invariants are proved inductive over the
transcribed `QStep`, `R` is the `U32.val`-as-Int simulation relation, and
per-action forward-simulation lemmas give `rust_refines_spec` so
`rust_b1..b4` transfer to every reachable extracted state
(`NonVacuity.lean` rules out vacuity). The finite-arithmetic gap (F2) is
carried as scope, not resolved: lemmas are ok-conditioned via
`UScalar.add_equiv`/`sub_equiv`, so totality at u32::MAX is not claimed
(F2 stays OPEN).

What remains before `REFINEMENT_VERIFIED` is ever emitted: (1) a
Quint-line citation gate binding each action definition in
`JobqRefinement.lean` to the action's line range in `jobq.qnt`, so the
hand-written transcription cannot drift from the spec silently — this is
the blocker; (2) the label, when built, must be scoped, e.g.
`REFINEMENT_VERIFIED[forward, CAPACITY=2, ok-conditioned, finite-arith
excluded per F2]`, never bare (G3, R26). Optional extensions: two-sided
refinement (reverse simulation + guard alignment, ~10 lemmas), other
capacities, and resolving F2 with checked-arithmetic Quint modeling. The
doctor still reports Verus not installed; install it if the Verus layer
should participate.

### W6. Housekeeping (owner: user unless noted)

- `gpt-5.6-pro`: blocked by an account-level error at dispatch ("not supported
  when using Codex with a ChatGPT account"). When the account is fixed, one
  dispatch + score calibrates it (agent).
- `deepseek-v4-flash`: requires the local ds4 endpoint (DwarfStar4 at
  `http://127.0.0.1:8000`) to be running; then calibrate on the W2 corpus.
- `gemini-3.1-pro-preview`: requires `GOOGLE_GENERATIVE_AI_API_KEY` (or an
  opencode Google credential); then calibrate on the W2 corpus.
- `colosseum_doctor` OAuth false-warn: FIXED 2026-07-13 (checks all three
  opencode credential paths, not just env vars).
- Push `main`: DONE 2026-07-14 (github.com:reliqlabs/colosseum). The
  `scratchpad/` private review narrative is gitignored so a stray
  `git add -A` can never sweep it into a push.

### jobq spec strengthening — DONE 2026-07-14 except F2 (commit 61e6588)

The 2026-07-13 panel attack on the R22 fixture
(`dogfood/jobq-2026-07-13/ADJUDICATION.md`) found real spec-quality gaps in
our own reference project; the dogfood loop closed by fixing them (INTENT
v1.1, `specs/jobq.qnt`, obligations B5/W2, rebound ledger, adapter, R22
suite):
- F1: `inv_b3` is now the biconditional (idle => attempts 0, running =>
  1..MAX) plus `inv_nonneg`, so the invariant set stands alone;
- F3+F6: `CAPACITY` parameterized (`jobqP` module), verified at 2 and 4,
  default 2 made distinct from MAX_ATTEMPTS 3; both former mutants
  (constant swap, capacity pin) now produce counterexamples;
- F4: terminal monotonicity encoded with ghost prev-counters as required
  target B5; the `clawback` mutant now fails verify;
- F7: failure-path witness W2 (`witness_b1_failed`) added as an obligation;
- F5: INTENT K3 scopes error VALUES out of replay conformance (rejection is
  modeled as action absence; error enums are unit-tested and ledger-cited);
- F8 (process): panel attack copies must carry the full project.
- **F2 remains OPEN**, by design, as the recorded contested finding (Quint
  proves conservation over unbounded int; the code is u32). Resolving it
  needs either checked-arithmetic Quint modeling or a justified
  submission-bound trust assumption, plus new evidence, not a vote.

Also fixed in the same push (c363545): a latent broken-clone bug the
strengthening surfaced. The global `.colosseum/` gitignore had hidden every
fixture manifest (r22 obligations/ledger/floors, four r28 floors.json) from
git, so local CI passed while fresh clones failed r22/r28. Negated the
ignore for `tests/fixtures/`, tracked the seven manifests, and added a
`fixture-tracking` CI check (verified by cloning fresh and running r22
green off the clone) so an untracked fixture can never ship a broken clone
again.

### GitHub Actions CI — green since 2026-07-14 (commits 4de698d, 82477ae)

The `colosseum-ci` workflow had failed on every push since it was added on
2026-07-12: four suites hard-failed on the toolchain-less runner instead of
degrading to the INCOMPLETE the workflow was designed to tolerate. Local
`ci.py` never saw it because this machine has the tools. Fixes:

- `opencode_dispatch.py`: the opencode-binary check lived inside the
  preflight scan, so `--preflight-only` runs (which never dispatch) and the
  `--voices`/`--slices` validation paths wrongly required the binary. Split
  into an `ensure_dispatch_ready()` gate that runs only once a real
  dispatch is committed. R3 (real dispatch, binary absent -> INCOMPLETE) is
  preserved; the preflight scan is file-safety only.
- `m3b`: stub invoked via `sys.executable` instead of a bare `python3` that
  `uv run` on a bare runner may not expose; a missing summary degrades to
  SKIP instead of a traceback.
- `r16/r17/r18`: probe for `cargo-kani` itself, not plain `cargo` (stock
  runners ship cargo without kani).

Getting past those exposed a SECOND broken-clone bug of the c363545 class:
`tests/fixtures/m3b/target` (a review-TARGET fixture, not a build dir) was
swallowed by the global Rust `target/` ignore, so fresh clones had no
benchmark target. The fixture is now tracked, and the fixture-tracking
check was replaced by `scripts/check_fixture_tracking.py` (self-tested),
which also flags ignore-HIDDEN fixtures — the blind spot both clone bugs
shared, since `git ls-files --others --exclude-standard` never lists
ignored files. Real build/run artifacts (a `target/` next to a Cargo.toml,
`.colosseum/verify/`) stay tolerated. Verified off a fresh clone and on
the live runner; both workflow jobs green.

## Suggested sequence

W1, W2, and W5 are done; W3 waits on a discriminating W2-iteration corpus.
The repo is pushed and CI is green, so W4 now waits only on an external
party picking up `docs/replication-protocol.md`. Remaining W6 items land
whenever their inputs appear (account fix, ds4 endpoint, Google credential).

## Provenance

The full remediation plan of record (contracts G1-G5, phases Z/E/C/M, fixtures
R1-R28, exit criteria) came out of a five-round dual-agent adversarial review
closed 2026-07-11. Its narrative lives outside the repo; everything actionable
from it is either implemented (see the scoreboard) or captured above. Fixture
map: `tests/README.md`. Voice evidence: `registry/voices.json` and
`calibration/2026-07-13-r1/README.md`.
