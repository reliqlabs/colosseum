# colosseum/scripts/

Operational tooling that supports the methodology but is not itself part of any single skill. Currently houses the harness-agnostic dispatch manifest:

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

The manifest is also the natural place to record *failure shape* — `error_detail` captures the HTTP 408 / 524 / unloaded-model / cloudflare-page distinctions the verified-rcv Round 3a dogfood pass surfaced. Synthesis can reason about *why* a voice failed, not just *that* it did.

### Methodology back-port status (v0.3 ask)

This tool is the prototype for the harness-agnostic-dispatch v0.3 ask. The `colosseum-adversarial` SKILL.md currently describes harness-specific recipes (Claude Code Agent + lm-studio-mcp + external-model-mcp). The v0.3 shape should describe the manifest protocol once, then ship per-harness appendices (Claude Code recipe, OpenCode recipe, shell recipe) all pointing at the same manifest format.

Round 3a (verified-rcv) is the first project to dogfood it end-to-end.
