# external-model-mcp

MCP server exposing non-Anthropic frontier providers as Claude-callable tools. Three surfaces:

- **OpenAI** direct API
- **Google Gemini** direct API
- **A configurable OpenAI-compatible gateway** (URL + key loaded from `.env`; routes to one or more upstream providers behind a single endpoint)

The infrastructure layer beneath Colosseum's multi-model adversarial work — without it, "adversarial beats consensus" is single-model in practice.

Anthropic models are already native to Claude Code; this MCP fills the gap for genuine family diversity. The gateway surface adds a second access path: when you have a gateway routing Claude tiers (or any other provider) under an OpenAI-format API, the MCP treats it as just another callable provider.

## Design contract

Single-shot completions only. No tool-use loops, no agentic behavior. The `colosseum-adversarial` skill inlines all artifacts (spec + intent + context) into one prompt, dispatches it in parallel across providers, and persists each response verbatim.

Why single-shot: an adversarial review is a structured one-pass task. Adding agentic loops to non-Claude providers would multiply complexity without adding correctness (the adversary's job is to read and report, not to explore the codebase). When deeper exploration is needed, Claude orchestrates from above.

## Tools

### `check_external_health`

Probe each configured provider (key present + endpoint reachable). Reports per provider:
- whether the API key is set
- whether a model-list call succeeded
- sample of available models
- the configured default model

### `query_openai(prompt, model?, temperature?, max_tokens?, system_prompt?)`

Single-shot completion via OpenAI chat completions. Returns `text`, `finish_reason`, `usage`, `model_returned`.

### `query_google(prompt, model?, temperature?, max_tokens?, system_prompt?)`

Single-shot completion via Google Gemini's `generateContent`. Returns the same shape as `query_openai`.

### `query_gateway(prompt, model?, temperature?, max_tokens?, system_prompt?)`

Single-shot completion via the configured multi-model gateway (OpenAI-format). Returns the same shape as `query_openai`. Requires both `COLOSSEUM_GATEWAY_API_KEY` and `COLOSSEUM_GATEWAY_BASE_URL` to be set; if either is missing, returns a configuration error. `model` defaults to `COLOSSEUM_GATEWAY_DEFAULT_MODEL` if set; otherwise the caller must supply one.

### `fan_out_query(prompt, providers?, temperature?, max_tokens?, system_prompt?)`

Send the same prompt to multiple providers **in parallel** and return all responses. The load-bearing tool for adversarial work — one call gets you family-diverse responses to the same question.

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `prompt` | string | — | Identical across providers |
| `providers` | list? | all configured | Subset of `["openai", "google", "gateway"]` |
| `temperature` | float | 0.7 | Applied uniformly |
| `max_tokens` | int | 4096 | Applied uniformly |
| `system_prompt` | string? | null | Applied uniformly |

Returns `{ "providers_queried": [...], "responses": { "openai": {...}, "google": {...}, "gateway": {...} } }` — only entries for queried providers are present.

## Setup

### 1. Obtain credentials

- OpenAI: https://platform.openai.com/api-keys
- Google Gemini: https://aistudio.google.com/apikey
- Gateway: URL + key from whichever multi-model gateway you're using

### 2. Configure via `.env` (recommended)

Copy `<colosseum-repo>/.env.example` to one of these locations (in load order):

1. `$COLOSSEUM_DOTENV` (explicit override path)
2. `./.env` in the working directory you launch Claude from
3. `<colosseum-repo>/.env` (alongside this MCP)
4. `~/.colosseum.env` (user-global)

Fill in only the keys you have. All `.env` files matching `*.env` are gitignored except `.env.example`. Existing shell-exported environment variables take precedence over `.env` values.

### 3. Register with Claude Code

```json
{
  "mcpServers": {
    "external-model": {
      "command": "/Users/mvid/Development/reliq/colosseum/mcp/external-model-mcp/external_model_mcp.py",
      "env": {}
    }
  }
}
```

The `env` block is empty because credentials come from `.env`. (If you prefer the credentials live in `~/.claude.json`'s `env` block instead of `.env`, that also works — but be aware that file is generally less protected and more easily synced into backups than a gitignored `.env`.)

### 4. Verify

```
mcp__external_model__check_external_health()
```

Expected: `ok: true` with at least one provider's `reachable: true`.

## Configuration

| Var | Default | Purpose |
|-----|---------|---------|
| `OPENAI_API_KEY` | — | OpenAI auth (omit to disable that provider) |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Override for Azure / proxies |
| `OPENAI_DEFAULT_MODEL` | `gpt-4o` | Default for `query_openai` |
| `GEMINI_API_KEY` or `GOOGLE_API_KEY` | — | Google auth (omit to disable that provider) |
| `GOOGLE_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta` | |
| `GOOGLE_DEFAULT_MODEL` | `gemini-2.0-flash-exp` | Default for `query_google` |
| `COLOSSEUM_GATEWAY_API_KEY` | — | Gateway auth (URL also required for gateway to be active) |
| `COLOSSEUM_GATEWAY_BASE_URL` | — | Gateway endpoint URL (no default — must be set via `.env` / shell) |
| `COLOSSEUM_GATEWAY_DEFAULT_MODEL` | — | Optional default model id for `query_gateway` |
| `COLOSSEUM_DOTENV` | — | Optional override path for the `.env` to load |
| `EXTERNAL_MODEL_TIMEOUT_S` | `300` | Per-request timeout |

## Typical usage pattern

In a Colosseum adversarial session targeting family diversity:

1. Claude reads the spec + intent
2. Claude crafts a single adversarial prompt that inlines both artifacts and instructs the recipient to attack per the `colosseum-spec-adversary` system prompt
3. Claude calls `fan_out_query(prompt, providers=["openai", "google", "gateway"])` to get parallel attacks across families
4. (Optional) Claude also runs `colosseum-spec-adversary` natively (Claude's own attack from inside the harness)
5. The `colosseum-adversarial` skill persists each response verbatim under `.colosseum/attacks/<spec>-<timestamp>/<voice-id>.md`
6. Claude surfaces the overlap/divergence per the three-section synthesis format (overlap matrix / false positives / methodology disagreement)

When the adversarial roster includes models that this MCP cannot reach (e.g., local LM Studio voices, or kimi-k2 / glm-4 / gpt-oss routed through the same gateway via voice-specific OpenAI clients with finer-grained timeout control), use `colosseum_run.py` to coordinate a multi-harness run via the shared `run.json` manifest. See `colosseum/scripts/README.md`.

## Cost notes

API calls cost money. Default `colosseum-adversarial` runs use Claude only; cloud diversity is opt-in via the skill's `models` parameter. Recommended pattern: local floor (always-on, free) → Claude (always-on, billed via subscription) → cloud diversity (opt-in for high-stakes spec milestones).

OpenAI gpt-4o-mini and Gemini 2.0 Flash are cheap enough for routine adversarial work; gpt-4o and Gemini 1.5 Pro are reserved for high-stakes runs. Set `OPENAI_DEFAULT_MODEL` / `GOOGLE_DEFAULT_MODEL` accordingly. Gateway billing depends on the gateway's upstream pricing — typically pass-through plus a flat margin; budget per the upstream model id you pass.

## Status

Single-shot completions to OpenAI, Google, and a configurable OpenAI-format gateway. Parallel fan-out across all three surfaces. No streaming, no tool-use, no retries on transient errors (transient errors surface as the response and the orchestrating skill decides whether to retry).

Features:

- Gateway provider as a first-class fan-out target (any OpenAI-format multi-model gateway, e.g., routing Claude / Kimi / GLM / GPT-OSS under one endpoint)
- `.env` load order documented across four locations; `COLOSSEUM_DOTENV` override
- `query_gateway` returns the same shape as `query_openai`, so synthesis code is provider-agnostic

Known gaps:

- No retry / backoff. Rate limits and transient gateway errors surface as raw API errors.
- No per-route timeout override. The MCP uses one `EXTERNAL_MODEL_TIMEOUT_S` for every call; some gateway routes have observed hard caps below this (see `verified-rcv/.colosseum/gateway-bugs-2026-05-14.md` Bug 3, Bug 4). When a route's effective cap is known to be lower than the MCP default, dispatch via a dedicated script (e.g., `verified-rcv/.colosseum/scripts/fan_out_dispatch.py`) rather than through the MCP.
- No token-budget enforcement at the MCP layer. Use `max_tokens` to bound costs.
- No streaming support. Adversarial reviews are bounded-length so this is acceptable.
- `temperature` is sent uniformly; some upstream models (e.g., `claude-opus-4-7` via gateway) reject `temperature` and require it to be omitted. Workaround: handle in the calling script, not the MCP.

## Future work

- Per-route timeout and per-route `temperature` exclusion (would let the MCP handle gateway voices that currently must go through bespoke dispatch scripts)
- Retry-with-backoff on 429 / 5xx, with a route-aware deny-list for known-broken upstream paths
- Per-provider cost-cap enforcement and usage tracking
- Optional health-probe variant that distinguishes "gateway reachable" from "specific upstream route reachable" (relevant once gateway adds more routes than the health endpoint can sample)
