# lm-studio-mcp

General-purpose wrapper for local models served via LM Studio's OpenAI-compatible endpoint. The **adversarial floor** of Colosseum's multi-model story: zero marginal cost, genuine architectural diversity (different training data, different RLHF lineage than Claude / GPT / Gemini), always-on.

Separate from [`goedel-mcp`](../goedel-mcp/), which is specialized for Lean tactic proposal. This MCP is the general voice — adversarial review, synthesis, anything where a non-frontier-but-architecturally-different opinion is valuable.

## Why local diversity matters

The methodology's "adversarial beats consensus" claim depends on family diversity. Two LLMs from the same lineage agreeing tells you they share blind spots. Two from genuinely different lineages disagreeing surfaces a real ambiguity.

Local models like Qwen and Gemma have **different blind spots** from Claude — different pretraining data, different RLHF, different fine-tuning. They are not frontier-quality on most tasks, but for adversarial review of a spec they don't need to be: they need to be wrong in different ways than Claude.

Local also means free. The floor of adversarial review can run on every spec without budget anxiety; cloud diversity (external-model-mcp) is reserved for high-stakes milestones.

## Tools

### `check_lmstudio_health`

Verify the OpenAI-compatible endpoint is reachable, list loaded models, run a minimal completion probe against the first loaded model.

### `list_loaded_models`

Return the current set of loaded model ids in LM Studio. Useful before `fan_out_local` to pick targets.

### `query_local(prompt, model?, temperature?, max_tokens?, system_prompt?)`

Single-shot completion against one local model. Defaults to `LMSTUDIO_DEFAULT_MODEL` env var, or the first loaded model.

### `fan_out_local(prompt, models?, temperature?, max_tokens?, system_prompt?)`

Same prompt against multiple loaded local models in parallel. Returns a dict keyed by model id.

**Hardware caveat:** parallel local inference contends for the same GPU. On consumer hardware, two parallel calls to two large dense models effectively serialize at the LM Studio scheduler. Pair small models (Qwen 3.5 small + Gemma 3 small) for genuine concurrency, or accept the sequential execution and let the parallelism just save round-trip latency.

## Setup

### 1. Configure LM Studio

- Install LM Studio (https://lmstudio.ai)
- Load at least one model (recommended for adversarial diversity: a Qwen and a Gemma — different lineages)
- Enable the **Developer** tab → **Server** → start the server on the default port (1234)
- Confirm the OpenAI-compatible endpoint is reachable: `curl http://localhost:1234/v1/models`

### 2. Register with Claude Code

```json
{
  "mcpServers": {
    "lm-studio": {
      "command": "/Users/mvid/Development/reliq/colosseum/mcp/lm-studio-mcp/lm_studio_mcp.py"
    }
  }
}
```

To set a default model:

```json
{
  "mcpServers": {
    "lm-studio": {
      "command": "/Users/mvid/Development/reliq/colosseum/mcp/lm-studio-mcp/lm_studio_mcp.py",
      "env": {
        "LMSTUDIO_DEFAULT_MODEL": "qwen-3.6-27b-instruct"
      }
    }
  }
}
```

### 3. Verify

```
mcp__lm_studio__check_lmstudio_health()
```

Expected: `ok: true` with `loaded_models` listing your active models.

## Configuration

| Var | Default | Purpose |
|-----|---------|---------|
| `LMSTUDIO_BASE_URL` | `http://localhost:1234/v1` | LM Studio API endpoint |
| `LMSTUDIO_DEFAULT_MODEL` | first loaded | Used when `query_local` has no model arg |
| `LMSTUDIO_TIMEOUT_S` | `300` | Per-call timeout |

## Recommended adversarial pairings

For diverse blind-spot coverage with manageable concurrency cost on a consumer GPU:

| Pair | Rationale |
|------|-----------|
| Qwen 3.6 (small) + Gemma 3 (small) | Different lineages, both fast; clean concurrency |
| Qwen 3.6 27B + Gemma 3 27B | Stronger reasoning; expect serialization on shared GPU |
| Single big model + fan_out only when budget allows | Avoids GPU contention; loses some diversity |

Models smaller than ~7B are usually too weak for spec-attack quality. The sweet spot for adversarial floor work is in the 12B–32B band with MoE preferred for speed.

## Typical usage pattern

In a Colosseum adversarial session:

1. Claude calls `list_loaded_models()` to see what's available
2. Claude crafts a single adversarial prompt inlining spec + intent
3. Claude calls `fan_out_local(prompt, models=["qwen-3.6-27b-instruct", "gemma-3-27b-it"])` to get parallel local attacks
4. Each model's attack is persisted verbatim by the `colosseum-adversarial` skill
5. Combined with cloud diversity from `external-model-mcp` (if opted in), the result is a true multi-family attack on the spec

The local floor's job is *not* to find the same bugs Claude or GPT would find — it is to occasionally find something they all missed because of their shared lineage. One genuine catch per quarter justifies the always-on cost (which is zero).

## Status

**v0.1** — Single-shot and fan-out completions against LM Studio's OpenAI-compatible endpoint. Compatible with any LM Studio version that supports the developer API.

Known gaps:

- No streaming. Adversarial reviews are bounded-length so this is acceptable.
- No GPU-contention awareness. The MCP fans out blindly; LM Studio handles the actual scheduling. If two parallel calls effectively serialize, callers should reduce parallelism manually.
- Doesn't probe model context-length capacity before sending. A prompt larger than the model's loaded context will fail at LM Studio with an opaque error.

## Future work

- Probe model context-length on `list_loaded_models` so callers can size prompts accordingly
- Add `query_local_with_speculative` once LM Studio's spec-decoding API surface is exposed for general models
- Adapter for non-LM-Studio local servers (ollama, vLLM) that already expose OpenAI-compatible endpoints — likely just a matter of `LMSTUDIO_BASE_URL` override but worth documenting
