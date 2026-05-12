# external-model-mcp

MCP server exposing **non-Anthropic** frontier providers (OpenAI, Google Gemini) as Claude-callable tools. The infrastructure layer beneath Colosseum's multi-model adversarial work — without it, "adversarial beats consensus" is single-model in practice.

Anthropic models are already native to Claude Code; this MCP fills the gap for genuine family diversity.

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

### `fan_out_query(prompt, providers?, temperature?, max_tokens?, system_prompt?)`

Send the same prompt to multiple providers **in parallel** and return all responses. The load-bearing tool for adversarial work — one call gets you family-diverse responses to the same question.

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `prompt` | string | — | Identical across providers |
| `providers` | list? | all configured | Subset of `["openai", "google"]` |
| `temperature` | float | 0.7 | Applied uniformly |
| `max_tokens` | int | 4096 | Applied uniformly |
| `system_prompt` | string? | null | Applied uniformly |

Returns `{ "providers_queried": [...], "responses": { "openai": {...}, "google": {...} } }`.

## Setup

### 1. Obtain API keys

- OpenAI: https://platform.openai.com/api-keys
- Google Gemini: https://aistudio.google.com/apikey

### 2. Register with Claude Code

```json
{
  "mcpServers": {
    "external-model": {
      "command": "/Users/mvid/Development/reliq/colosseum/mcp/external-model-mcp/external_model_mcp.py",
      "env": {
        "OPENAI_API_KEY": "sk-...",
        "GEMINI_API_KEY": "..."
      }
    }
  }
}
```

Either key alone works — the MCP gracefully reports only the configured providers. Both keys give full coverage.

### 3. Verify

```
mcp__external_model__check_external_health()
```

Expected: `ok: true` with at least one provider's `reachable: true`.

## Configuration

| Var | Default | Purpose |
|-----|---------|---------|
| `OPENAI_API_KEY` | — | OpenAI auth (omit to disable) |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Override for Azure / proxies |
| `OPENAI_DEFAULT_MODEL` | `gpt-4o` | Default for `query_openai` |
| `GEMINI_API_KEY` or `GOOGLE_API_KEY` | — | Google auth (omit to disable) |
| `GOOGLE_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta` | |
| `GOOGLE_DEFAULT_MODEL` | `gemini-2.0-flash-exp` | Default for `query_google` |
| `EXTERNAL_MODEL_TIMEOUT_S` | `300` | Per-request timeout |

## Typical usage pattern

In a Colosseum adversarial session targeting family diversity:

1. Claude reads the spec + intent
2. Claude crafts a single adversarial prompt that inlines both artifacts and instructs the recipient to attack per the `colosseum-spec-adversary` system prompt
3. Claude calls `fan_out_query(prompt, providers=["openai", "google"])` to get parallel attacks
4. (Optional) Claude also runs `colosseum-spec-adversary` natively (Claude's own attack)
5. The `colosseum-adversarial` skill persists each response verbatim under `.colosseum/attacks/<spec>-<timestamp>/<provider>.md`
6. Claude surfaces the overlap/divergence — which findings are shared (multi-provider consensus on a real bug), which are unique to one model (potential blind-spot escape)

## Cost notes

API calls cost money. Default `colosseum-adversarial` runs use Claude only; cloud diversity is opt-in via the skill's `models` parameter. Recommended pattern: local floor (always-on, free) → Claude (always-on, billed via subscription) → cloud diversity (opt-in for high-stakes spec milestones).

OpenAI gpt-4o-mini and Gemini 2.0 Flash are cheap enough for routine adversarial work; gpt-4o and Gemini 1.5 Pro are reserved for high-stakes runs. Set `OPENAI_DEFAULT_MODEL` / `GOOGLE_DEFAULT_MODEL` accordingly.

## Status

**v0.1** — Single-shot completions to OpenAI and Google. Parallel fan-out tool included. No streaming, no tool-use, no retries on transient errors (transient errors surface as the response and the orchestrating skill decides whether to retry).

Known gaps:

- No retry / backoff. Rate limits surface as raw API errors.
- No token-budget enforcement at the MCP layer. Use `max_tokens` to bound costs.
- No streaming support. Adversarial reviews are bounded-length so this is acceptable for v0.1.

## Future work

- Add Anthropic as a fan-out target (currently redundant inside Claude Code, but useful from non-Claude clients)
- Retry-with-backoff on 429 / 5xx
- Per-provider cost-cap enforcement and usage tracking
