# colosseum/scripts/

Operational tooling that supports the methodology but is not itself part of any single skill.

## `opencode_dispatch.py` — canonical OpenCode adversarial orchestrator

**Purpose.** The Mode 1 dispatch path described in `colosseum/skills/colosseum-adversarial/SKILL.md`. Drives the `spec-adversary` OpenCode agent against a target spec across a roster of voices (gateway-routed `burnt/*` frontier voices plus local `lmstudio/*` voices), one (voice, slice) pair per `opencode run` invocation. Captures stdout, detects truncated stubs, retries on failure, aggregates per-voice files plus a summary.

**This is the primary dispatch surface for non-Claude voices.** The `external-model-mcp` MCP tools (`query_gateway`, `query_openai`, `query_google`, `fan_out_query`) are Mode 3 fallbacks, not this script's purpose. Reach for the MCP tools only when OpenCode is not installed on the host.

**Usage.** Copy this script to `<project>/.colosseum/scripts/opencode_dispatch.py` and supply a per-project config at `<project>/.colosseum/dispatch.json`:

```bash
uv run --script <project>/.colosseum/scripts/opencode_dispatch.py \
    --config <project>/.colosseum/dispatch.json \
    [--voices=A,B,C] [--slices=X,Y] [--sequential]
```

Config schema is documented in `dispatch.config.example.json` alongside this script. Required fields: `project_root`, `target_spec`, `run_tag_prefix`, `voices[]`, `slices[]`. Optional: `context_appendix`, `per_call_timeout`, `max_retries`.

**Output.** `<project_root>/.colosseum/attacks/<run-tag>/` containing `per-section/<voice>/<slice>.md` (one per call), `opencode-<voice>.md` (per-voice aggregate), `dispatch.log`, `summary.json`.

**Required OpenCode configuration.** `~/.config/opencode/opencode.jsonc` must define the `burnt` and `lmstudio` providers and set `limit.output ≥ 65536` (recommend `131072`) per gateway model so the analysis response budget never hits a cap mid-report.

## `install-agents.py` — install the canonical agent bodies into a target harness

Builds per-harness agent wrappers (Claude Code subagent or OpenCode subagent) from the canonical bodies under `colosseum/agents/*-body.md`. Run before the first OpenCode dispatch in a new project:

```bash
colosseum/scripts/install-agents.py install --harness opencode --target <project>/.opencode/agent/
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
      "id":            "<voice-id, e.g. 'kimi-k2-6' or 'claude'>",
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
colosseum_run.py init \
    /path/to/.colosseum/intent.md \
    --voices=claude,kimi-k2-6,glm-4-7-flash,gpt-oss-120b,mistral-119b,qwen3.6,gemma-26b \
    --owners=claude:claude-code,kimi-k2-6:opencode,glm-4-7-flash:opencode,gpt-oss-120b:opencode,mistral-119b:opencode,qwen3.6:opencode,gemma-26b:opencode

# Phase 2a — Claude Code harness dispatches its assigned voice(s):
#   • spawns the Agent subagent with full tool access
#   • subagent writes to <run-dir>/claude.md
#   • harness marks the voice complete
colosseum_run.py complete <run-dir> --voice=claude --elapsed=339 --finish-reason=stop

# Phase 2b — OpenCode harness dispatches its assigned voice(s) in parallel.
# Each non-Claude voice is an OpenCode subagent with file-access tools + step
# budget. OpenCode marks each complete as it lands.
colosseum_run.py complete <run-dir> --voice=kimi-k2-6 --elapsed=520 --finish-reason=stop
colosseum_run.py error    <run-dir> --voice=goedel-32b --detail="degenerated into tautology loops" --elapsed=852

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

This tool is the prototype for harness-agnostic dispatch. The `colosseum-adversarial` SKILL.md currently describes harness-specific recipes (Claude Code Agent + lm-studio-mcp + external-model-mcp). The intended shape: describe the manifest protocol once, then ship per-harness appendices (Claude Code recipe, OpenCode recipe, shell recipe) all pointing at the same manifest format.

Verified-rcv was the first project to dogfood it end-to-end.
