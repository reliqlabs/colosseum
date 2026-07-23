# OMP-native deliberation-panel E2E smoke — 2026-07-23

A true project-rooted end-to-end run of the `colosseum-panel` skill through a
nested `omp -p` session, proving the live seam that the deterministic R31 suite
cannot: `exec(read("skill://…"))` module loading, roster resolution, the real
OMP `agent()` / `parallel()` bridge (with `agent=`, per-call `model=`,
`handle=True`, and `schema=`), three barriered waves with blinded cross-review,
synthesis, and evidence persistence. Machine artifacts were ephemeral (temp
project, since deleted); the durable facts are recorded here.

## Setup

- Clean temp project scaffolded with `colosseum_init.py --harness omp` (panel
  skill, panelist/synthesizer agents, resolver extension, profile, `.colosseum/panels/`,
  and harness marker all installed; no `.opencode/` artifacts).
- A cheap 3-family smoke profile (`min_families: 3`, thinking `low`) so the run
  proves the machinery without premium spend:
  - Anthropic — `anthropic/claude-haiku-4-5`
  - Moonshot — `kimi-k2.6-fast`
  - OpenAI — `gpt-5.4-mini`
  - synthesizer — `anthropic/claude-haiku-4-5`
  (The shipped `templates/omp-panel.json` targets the frontier tier —
  `gpt-5.6-sol`, `glm-5.2`, and `claude-fable-5`/`kimi-k3` with
  `claude-opus-4-8`/`kimi-k2.6` standing fallbacks while the premium seats are at
  capacity. This smoke deliberately uses cheaper reachable models.)
- Driver: `omp -p --cwd <proj> --model anthropic/claude-haiku-4-5 --auto-approve`
  running one eval cell that wired the skill as `SKILL.md` documented it at the
  time. Note: the roster step was subsequently hardened to fail closed (require
  the `colosseum-panel-resolver` extension; no stdlib fallback for execution), so
  this run's roster-resolution path no longer matches the documented wiring; see
  "What this does NOT establish". The engine/bridge/blinding/coverage machinery
  it exercised is unchanged.

## Result (from the run's `summary.json`, since deleted with the temp project)

- **`run_status`: COMPLETE**, `route_hash: sha256:25b5610485eb30d6`, wall 179 s.
- Quorum: 3/3 drafts ok, 3/3 reviews ok, 3 distinct families
  (Anthropic, Moonshot, OpenAI), `review_quorum_met` and
  `review_coverage_complete` both true; synthesis ok.
- `brief_stable: true`. `target_revision.available: false` (temp project is not a
  git work tree, so drift could not be enforced — recorded, not asserted).
- `isolation: unverified` (session confirmed rooted at `project_root` via the
  `PI_SESSION_FILE` header; filesystem confinement is not mechanically verified).
- `preflight: ok` (clean tree scanned before any model call).

Per-seat (dispatch selector shows the requested thinking level folded in):

| phase | family | dispatch selector | status | elapsed | bytes |
|---|---|---|---|---|---|
| draft | Anthropic | `anthropic/claude-haiku-4-5:low` | ok | 35.0s | 6576 |
| draft | Moonshot | `kimi-k2.6-fast:low` | ok | 25.7s | 4707 |
| draft | OpenAI | `gpt-5.4-mini:low` | ok | 43.2s | 4596 |
| review | Anthropic | `anthropic/claude-haiku-4-5:low` | ok | 66.2s | 5731 |
| review | Moonshot | `kimi-k2.6-fast:low` | ok | 30.6s | 4818 |
| review | OpenAI | `gpt-5.4-mini:low` | ok | 44.6s | 4956 |
| synthesis | (Anthropic) | `anthropic/claude-haiku-4-5:low` | ok | 55.6s | 8926 |

## What this establishes (live, not simulated)

- The skill loads via `exec(read("skill://colosseum-panel/…"))` and drives the
  real `agent()` / `parallel()` bridge; real models returned schema-conforming
  structured output that `_extract` parsed into `drafts/*.json`,
  `reviews/*.json`, and `final.json`.
- **Blinding held on disk.** Anonymous labels were assigned in random order
  (`moonshot→A, openai→B, anthropic→C` — not profile order); every per-seat file
  was named by label only; `route.json`/`meta.json` (the de-anonymizing map) were
  written only at finish; and a grep of the review prompts for any model/family
  identity returned nothing.
- Thinking level was preserved end-to-end via the composed `model:level`
  dispatch selector.
- Three barriered waves executed with real family diversity and full coverage.

## What this does NOT establish

- **Panel quality / calibration.** OMP routes remain `calibration: pending`; there
  is still no evidence a panel beats a single `@plan`/`@advisor` pass. This smoke
  proves the machinery runs, not that its output is better.
- The frontier-tier roster (`gpt-5.6-sol` + `glm-5.2` + fable/kimi3) end-to-end —
  this smoke used cheaper reachable models; fable and kimi-k3 were at capacity.
- Git target-drift enforcement live (the temp project was not a git repo; R31
  covers this deterministically).
- The `colosseum-panel-resolver` extension's live `ctx.models.family` path. This
  run predates the fail-closed hardening and used the stdlib `panel_roster`
  loader (declared-label check only, no availability or opaque model-family
  check). The SKILL now REQUIRES the extension for panel execution and raises if
  it is absent, so this exact roster-resolution path is no longer permitted.
  RESOLVED 2026-07-24: the extension's live `ctx.models.family` path (positive,
  family-collision, and unavailable-candidate cases) is now exercised in
  `calibration/2026-07-24-resolver-live/`, which also fixed two defects that
  only a live run could surface.
- The **`milestone-review`** mode. This smoke is `project-plan` only.
  Milestone-review is EXPERIMENTAL: its evidence-bound fail-closed adjudication
  (Gate B binding, `--expect-intent`/`--snapshot-exact`, clean-tree + snapshot
  gates) is covered by deterministic tests (R31, incl. a real Gate B end-to-end
  over fixture records) but has not been run against a real project's
  itf_replay-produced G1 records with a live multi-model panel.
