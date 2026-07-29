# colosseum/scripts/

Operational tooling that supports the methodology but is not itself part of any single skill.

## `opencode_dispatch.py` — canonical OpenCode adversarial orchestrator

**Purpose.** The dispatch path described in `colosseum/skills/colosseum-adversarial/SKILL.md`. Drives the `spec-adversary` OpenCode agent against a target spec across a roster of voices (gateway-routed `burnt/*` frontier voices, direct-provider `openai/*`, `google/*`, and `fireworks-ai/*` voices, and local `lmstudio/*` and `ds4/*` voices), one (voice, slice) pair per `opencode run` invocation. Captures stdout, detects truncated stubs, retries on failure, aggregates per-voice files plus a summary.

**This is the calibrated reference and compatibility surface.** OMP may route the same registered non-Claude voices through its native agent bridge. Both transports run the repository-aware adversary; neither uses a single-shot MCP dispatch path.

**Usage.** Copy this script to `<project>/.colosseum/scripts/opencode_dispatch.py` and supply a per-project config at `<project>/.colosseum/dispatch.json`:

```bash
uv run --script <project>/.colosseum/scripts/opencode_dispatch.py \
    --config <project>/.colosseum/dispatch.json \
    [--voices=A,B,C] [--slices=X,Y] [--sequential]
```

Config schema is documented in `dispatch.config.example.json` alongside this script. Required fields: `project_root`, `target_spec`, `run_tag_prefix`, `voices[]`, `slices[]`. Optional: `context_appendix`, `per_call_timeout`, `max_retries`.

**Output.** `<project_root>/.colosseum/attacks/<run-tag>/` containing `per-section/<voice>/<slice>.md` (one per call), `opencode-<voice>.md` (per-voice aggregate), `dispatch.log`, `summary.json`.

**Required OpenCode configuration.** `~/.config/opencode/opencode.jsonc` must define the `burnt` and `lmstudio` providers and set `limit.output ≥ 65536` (recommend `131072`) per gateway model so the analysis response budget never hits a cap mid-report.

### Voice roster (authoritative source: `registry/voices.json`)

The adversarial voice roster is registry-driven. `registry/voices.json` is the source of truth; the table below and the roster blocks in the SKILLs, INSTALL, and `dispatch.config.example.json` are generated from it by `scripts/gen_roster_docs.py` (run `--check` in CI to fail on drift). The canonical panel (`canonical-4`) is `claude-agent` (Fable 5, or the strongest available Opus), `gpt-5.6-sol`, `glm-5.2`, and `kimi-k3`, all with cited seeded-recall fitness runs; the first three from `calibration/2026-07-13-r1` and `kimi-k3` from `calibration/2026-07-26-r2`, which also re-baselined the voice it replaced. `kimi-k2.6` (the prior Moonshot seat, superseded 2026-07-26), `gpt-oss-120b`, and `nemotron-3-120b-a12b` are calibrated candidates; `deepseek-v4-flash` and `gemini-3.1-pro-preview` await a fitness run.

<!-- BEGIN GENERATED: voice-roster (source: registry/voices.json via scripts/gen_roster_docs.py — do not edit by hand) -->
| Voice id | Reference model | OMP model | Family | Reference harness | Status | Reference calibration | OMP calibration |
|---|---|---|---|---|---|---|---|
| `claude-agent` | `in-harness` | `anthropic/claude-fable-5` | Anthropic | claude-code | canonical-panel | cited | pending |
| `kimi-k2.6` | `burnt/cloudflare-100/@cf/moonshotai/kimi-k2.6` | `burnt/cloudflare-100/@cf/moonshotai/kimi-k2.6` | Moonshot | opencode | candidate | cited | pending |
| `gpt-5.6-sol` | `openai/gpt-5.6-sol` | `openai-codex/gpt-5.6-sol` | OpenAI | opencode | canonical-panel | cited | pending |
| `deepseek-v4-flash` | `ds4/deepseek-v4-flash` | n/a | DeepSeek | opencode | candidate | pending | n/a |
| `gemini-3.1-pro-preview` | `google/gemini-3.1-pro-preview` | n/a | Google | opencode | candidate | pending | n/a |
| `gpt-oss-120b` | `burnt/cloudflare-100/@cf/openai/gpt-oss-120b` | n/a | OpenAI-OSS | opencode | candidate | cited | n/a |
| `nemotron-3-120b-a12b` | `burnt/cloudflare-100/@cf/nvidia/nemotron-3-120b-a12b` | n/a | NVIDIA | opencode | candidate | cited | n/a |
| `glm-5.2` | `fireworks-ai/accounts/fireworks/models/glm-5p2` | `fireworks/glm-5.2` | Zhipu | opencode | canonical-panel | cited | pending |
| `kimi-k3` | `fireworks-ai/accounts/fireworks/models/kimi-k3` | `fireworks/kimi-k3` | Moonshot | opencode | canonical-panel | cited | pending |
| `leanstral-2603` | `lmstudio/leanstral-2603` | n/a | Mistral | opencode | local-specialist | n/a | n/a |
| `glm-4.7-flash` | `burnt/cloudflare-100/@cf/zai-org/glm-4.7-flash` | n/a | Zhipu | opencode | excluded | cited | n/a |
| `goedel-prover-v2-32b` | `lmstudio/goedel-prover-v2-32b` | n/a | theorem-prover-specialist | opencode | excluded | cited | n/a |

Reference calibration applies only to the recorded OpenCode or Claude Code route. OMP calibration is tracked separately; `pending` native routes are experimental and cannot inherit the reference claim.
<!-- END GENERATED: voice-roster -->

## OMP-native adversarial fan-out

`skills/colosseum-adversarial/omp_fanout.py` is the OMP-native coordinator.
Load it in an OMP Python `eval` cell, resolve explicit voice IDs from
`.colosseum/dispatch.json` with `load_omp_native_config()`, then call
`run_omp_fanout(agent_fn=agent, parallel_fn=parallel, allow_unverified_isolation=True, ...)`.

Each model call runs the generated `colosseum-spec-adversary` agent with its own
ModelRegistry override. The helper preflights the live project tree, binds the
target-spec hash, catches failures per voice, and persists prompts, raw output,
errors, handles, timing, route metadata, and a terminal `summary.json` under a
new `.colosseum/attacks/<run>/` directory. A one-voice failure produces
`PARTIAL`; an all-failed wave produces `INCOMPLETE`.

Native dispatch is fail-closed on the session root: it refuses unless
`allow_unverified_isolation=True` and OMP was launched inside `project_root`
(checked against the documented `PI_SESSION_FILE` session-header `cwd`), before
any `agent()` call. Unlike the OpenCode Z2 worktree it does not confine the
subagent filesystem, so every run stamps `isolation:"unverified"` in
`meta.json`/`summary.json`; that label is a precondition record, not a
containment guarantee.

The initializer additively introduces a missing `omp_native` block without
rewriting existing project config. `--force` performs a full canonical reset.
OMP route calibration is independent from the OpenCode/Claude Code reference
evidence and currently `pending`. Transport fallback is never automatic.

## `check_ledger_references.py` — reference-integrity gate (Gate A)

Reference implementation of Gate A of the two-gate Step 8 CI check in `skills/colosseum-compose/SKILL.md`. Parses every `<file>:<line>` citation in a project's `.colosseum/ledger.md` (backtick-quoted or `code:`-annotated), confirms the file exists inside the canonical root and the cited line is in range, non-empty, and not comment-only (Rust `#[...]` attribute lines are valid targets). Citations may bind content with an `@sha256:<12hex>` suffix; bound citations fail when the line's content changes (`--suggest-hashes` prints the suffixes). Empty or zero-citation ledgers fail — no vacuous pass. Every `axiom:` occurrence needs a meaningful justification phrase. Per-link Kani coverage warns by default; `--strict-kani` upgrades to failures.

This gate checks that references hook into live code. It does not judge whether the evidence discharges any claim — that is Gate B.

```bash
# Copy into the project, then wire into CI:
cp colosseum/scripts/check_ledger_references.py <project>/.colosseum/scripts/
<project>/.colosseum/scripts/check_ledger_references.py <project>/.colosseum/ledger.md
# exit 0 = gate passed; 1 = drift detected; 2 = usage error
```

`--root` overrides the directory citations resolve against (defaults to the ledger's grandparent, i.e. the project root for a ledger at `<project>/.colosseum/ledger.md`).

## `check_evidence_records.py` — semantic evidence gate (Gate B)

Validates claim-ID-keyed G1 evidence records (JSON under `<project>/.colosseum/evidence/`) against the full binding set: snapshot, intent hash, manifest hash, profile, toolchain digests, command, configuration, seeds, raw-output hash, parser schema version, run ID, plus `evidence_class`, `result`, `scope`, and a mandatory `waiver` key. A record missing any field is rejected. Verdicts follow the G2 truth table: `FAILED` (exit 1) on any required-claim FAIL, `INCOMPLETE` (exit 3) on missing/invalid/stale records or unwaived assumptions, `VERIFIED[profile=...]` (exit 0, never bare VERIFIED) only when every required claim passes.

```bash
colosseum/scripts/check_evidence_records.py --records <project>/.colosseum/evidence/ \
  --manifest <project>/.colosseum/obligations.json --expect-snapshot <commit>
```

## `coverage_dashboard.py` — G1 coverage view (read-only; not a gate)

Renders a per-required-claim coverage table from typed G1 evidence records (same schema as `check_evidence_records.py`, plus the M5 versioned-envelope shape). Computes the same G2 verdict as Gate B but is a visibility tool, not an enforcement gate. `--check` is a self-conformance mode: exits nonzero if the dashboard's own rendered output would ever emit a bare (unqualified) `VERIFIED`.

```bash
coverage_dashboard.py --records <project>/.colosseum/evidence/ --require B1,B2,W1 [--json]
coverage_dashboard.py --records <project>/.colosseum/evidence/ --manifest <obligations.json> --check
```

## `recall_score.py` — seeded-defect recall scorer (P2 measurement instrument)

Given a seeded-defect corpus and per-voice detections, computes per-voice recall, panel recall, and the seeded defects no voice caught. Match rule: basename, category, and line within tolerance; a right-place wrong-category hit does not count. The published prospective run is under `calibration/2026-07-14-bench1/`.

```bash
recall_score.py --corpus <corpus.json> --detections <per-voice.json|findings.json> [--json]
```

## `benchmark_run.py` — pre-registered ablation-arm runner (P2 measurement instrument)

Runs the five pre-registered arms against a seeded target and scores each with `recall_score.py`. Every model call uses one dispatch template, overridable with `--dispatch-cmd` for fixtures. The corpus never enters a prompt or target directory. Errored dispatches are recorded and excluded, never scored as zero. Arm 5 gives each voice the deduplicated, authorship-blinded findings from other voices before round 2. `--dry-run` prints the plan. Exit 0 means all arms scored; 2 is a usage error; 3 is INCOMPLETE. The published prospective run is under `calibration/2026-07-14-bench1/`.

```bash
benchmark_run.py --corpus <corpus.json> --targets <dir-with-REVIEW-INSTRUCTIONS.md> \
  --voices <csv> --out <dir> [--arms ordinary,single,repeated,multi-family,adversarial] \
  [--repeats 3] [--dispatch-cmd '<template>'] [--dry-run]
```

## `self_measure.py` — adversarial-yield, cost, and routing metrics (P2 measurement instrument)

Reports Colosseum's own run artifacts. `yield` gives per-voice adversarial yield by severity and confirmed-vs-refuted at adjudication; `cost` attributes token cost per confirmed finding from opencode `--format json` event data and reports cost unmeasured (not zero) when the data is absent; `routing` computes the cheapest-capable-layer metric only over an explicit layer map, returning INCOMPLETE rather than a number when the label data is missing. Metric definitions live in `docs/self-measurement.md`.

```bash
self_measure.py yield   --findings <findings.json> [--run <manifest.json>] [--json]
self_measure.py cost    --events <opencode-events.json> [--findings <findings.json>] [--json]
self_measure.py routing --findings <findings.json> --layer-map <layer-map.json> [--json]
```

## `check_ledger_version.py` — ledger envelope version gate (M5)

Validates the `ledger_schema_version` field of a ledger envelope (`{"ledger_schema_version": "colosseum-ledger/v1", "records": [...]}`). A bare list or bare record is unversioned/v0 (valid, warns). Exit 0 for a recognized version or unversioned; exit 2 for an unknown version or a `records` object with no version. The record-consuming tools (`check_evidence_records.py`, `coverage_dashboard.py`) read either shape; the version never changes a verdict, it lets the change loop spot a schema migration.

```bash
check_ledger_version.py --ledger <project>/.colosseum/ledger.json [--json]
```

## `colosseum_init.py` — scaffold a project for a harness

Creates the `.colosseum/` evidence directories, copies the dispatch and Gate A/B
scripts with executable modes intact, installs the OpenCode agents, and writes
the project dispatch configuration. `--harness omp` additionally installs all
skills, the three generated OMP agents, and the six MCP definitions under the
project's `.omp/` directory:

```bash
export COLOSSEUM=/absolute/path/to/colosseum
colosseum/scripts/colosseum_init.py <project> --harness omp
```

Normal reruns preserve local agent, skill, and conflicting MCP definitions while
filling missing MCP servers. `--force` restores Colosseum-owned agents, skills,
scripts, and MCP entries but preserves unrelated MCP servers.

## `install-agents.py` — install the canonical agent bodies into a target harness

Builds per-harness agent wrappers for Claude Code, OpenCode, and OMP from the
canonical bodies under `colosseum/agents/*-body.md`.

```bash
colosseum/scripts/install-agents.py install --harness opencode --target <project>/.opencode/agent/
colosseum/scripts/install-agents.py install --harness omp --target <project>/.omp/agents/
colosseum/scripts/install-agents.py build   # regenerate all wrappers in-repo
colosseum/scripts/install-agents.py lint    # verify wrappers match canonical bodies (0 = clean)
```

## `colosseum_run.py` — multi-harness adversarial dispatch coordinator

**Purpose.** The `colosseum-adversarial` skill describes the *intent* of a multi-model adversarial pass (a set of voices attacking the same spec, results synthesized after). When the voices live in different harnesses — e.g. the Claude voice runs inside Claude Code with the Agent subagent + file access, and the non-Claude voices run inside OpenCode with native multi-provider subagents — the harnesses need a shared coordination contract.

`colosseum_run.py` is that contract, made concrete as a `run.json` manifest file. Each harness reads + updates the manifest as it dispatches; the manifest IS the state machine.

**No model calls.** This tool is pure file I/O. It cannot replace any voice; it only orchestrates the artifacts each voice produces.

### Manifest schema

```jsonc
{
  "run_id":  "<basename>-<ISO-UTC-timestamp>",
  "target":  "<absolute path to spec/intent under review>",
  "created": "<ISO-UTC-timestamp>",
  "voices": [
    {
      "id":            "<voice-id from registry/voices.json, e.g. 'kimi-k2.6' or 'claude-agent'>",
      "harness":       "<which harness owns dispatch: 'claude-code' | 'opencode' | 'shell' | ...>",
      "file":          "<filename relative to run dir, e.g. 'opencode-kimi-k2-6.md'>",
      "status":        "pending | complete | error | skipped",
      "elapsed_s":     123.4,       // optional, set on completion or error
      "finish_reason": "stop",       // optional, OpenAI-style
      "error_detail":  "HTTP 408",   // optional, set on error
      "metadata":      { /* harness-specific extras, ignored by this tool */ }
    }
  ],
  "synthesis": {
    "file":    "synthesis.md",
    "harness": "claude-code",       // synthesis is best done by a strong reasoner
    "status":  "pending"
  }
}
```

### Lifecycle

```
                           ┌───────────────────┐
                           │  init (any caller)│
                           │  → creates run    │
                           │    dir + manifest │
                           └────────┬──────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                                       ▼
    ┌─────────────────────┐               ┌─────────────────────┐
    │ Claude Code dispatch │              │  OpenCode dispatch   │
    │ → claude.md         │               │ → opencode-<v>.md    │
    │ → complete --voice  │               │ → complete --voice   │
    └──────────┬──────────┘               └──────────┬──────────┘
               │                                     │
               └──────────────────┬──────────────────┘
                                  ▼
                       ┌──────────────────────┐
                       │ wait / status checks │
                       │  manifest until all  │
                       │  voices terminal     │
                       └──────────┬───────────┘
                                  ▼
                       ┌──────────────────────┐
                       │ synthesize           │
                       │  → synthesis-input.md│
                       │  (verbatim concat +  │
                       │   verdict tally)     │
                       └──────────┬───────────┘
                                  ▼
                       ┌──────────────────────┐
                       │ Synthesis voice      │
                       │ (e.g. Claude Code)   │
                       │ → synthesis.md       │
                       └──────────────────────┘
```

### Usage

```bash
# Phase 1 — orchestrator creates the manifest. Owner mapping is required.
# Voice ids come from registry/voices.json (canonical-4 profile shown here;
# glm-4.7-flash and the goedel class are excluded — see the roster table above).
colosseum_run.py init \
    /path/to/.colosseum/intent.md \
    --voices=claude-agent,gpt-5.6-sol,glm-5.2,kimi-k3 \
    --owners=claude-agent:claude-code,gpt-5.6-sol:opencode,glm-5.2:opencode,kimi-k3:opencode

# Phase 2a — Claude Code harness dispatches its assigned voice(s):
#   • spawns the Agent subagent with full tool access
#   • subagent writes to <run-dir>/claude-agent.md
#   • harness marks the voice complete
colosseum_run.py complete <run-dir> --voice=claude-agent --elapsed=339 --finish-reason=stop

# Phase 2b — OpenCode harness dispatches its assigned voice(s) in parallel.
# Each non-Claude voice is an OpenCode subagent with file-access tools + step
# budget. OpenCode marks each complete as it lands.
colosseum_run.py complete <run-dir> --voice=kimi-k3 --elapsed=520 --finish-reason=stop
colosseum_run.py error    <run-dir> --voice=goedel-prover-v2-32b --detail="degenerated into tautology loops" --elapsed=852

# Phase 3 — anyone (CI, human, agent) blocks until all voices terminal:
colosseum_run.py wait <run-dir> --timeout=3600

# Phase 4 — build the synthesis-prompt body (no LLM call):
colosseum_run.py synthesize <run-dir> --out=synthesis-input.md

# Phase 5 — hand synthesis-input.md to a Claude (or other) synthesis voice
# that produces <run-dir>/synthesis.md. That handoff is done by the skill
# layer, not this tool.
```

### Inspection

```bash
colosseum_run.py status <run-dir>           # human-readable table; exits 0 if all done, 1 if pending, 2 if any error
colosseum_run.py status <run-dir> --json    # raw manifest
colosseum_run.py reset <run-dir> --voice=X  # flip a voice back to pending (e.g. to re-run kimi after fixing a gateway issue)
```

### Why a manifest, not a daemon?

A manifest is **inspectable** (`cat run.json`), **crash-resumable** (a half-finished run picks up from `status: pending`), and **harness-agnostic** (any program that can read+write JSON can participate). A daemon would be more responsive at the cost of becoming a fourth piece of infrastructure to operate.

The manifest is also the natural place to record *failure shape* — `error_detail` captures the HTTP 408 / 524 / unloaded-model / cloudflare-page distinctions surfaced by the verified-rcv dogfood pass. Synthesis can reason about *why* a voice failed, not just *that* it did.

### Methodology back-port status

This tool coordinates dispatch across two harnesses: the Claude voice via the Claude Code Agent subagent, and every non-Claude voice via OpenCode (`opencode_dispatch.py`). The manifest is the shared state machine when those two harnesses must run side by side and Claude must remain in-process.

Verified-rcv was the first project to dogfood it end-to-end.
