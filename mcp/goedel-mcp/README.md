# goedel-mcp

MCP server that exposes a locally-running Goedel-Prover-V2 instance (served via LM Studio) as a tactic-proposal tool for Claude Code or any MCP-compatible client.

This is the first piece of the Colosseum v1 backbone. It lets a generalist orchestrator (Claude) delegate Lean 4 tactic generation to a specialist prover (Goedel) while retaining orchestration, error recovery, and verification routing.

## Architecture

```
Claude Code
   │
   │ MCP tool call: propose_lean_tactic(goal_state)
   ▼
goedel-mcp ────────────────► LM Studio (localhost:1234)
                                  │
                                  ▼
                            Goedel-Prover-V2-32B (loaded)
                                  │
                                  ▼
                            Tactic candidates
   ◄──────────────────────────────┘
Claude Code
   │
   │ (verify candidate via lean-lsp-mcp, retry, or commit)
   ▼
```

## Tools

### `propose_lean_tactic`

Generate Lean 4 tactic candidates for a given proof goal.

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `goal_state` | string | — | The Lean proof goal, e.g. from `lean_goal` LSP query |
| `n` | int | 5 | Number of independent candidates to sample |
| `temperature` | float | 0.7 | Sampling temperature (0.0 = deterministic) |
| `max_tokens` | int | 256 | Per-candidate token budget |
| `hypotheses` | string? | null | Optional hypotheses-in-scope for the prompt |

Returns `{candidates: [string], metadata: {...}}`. Candidates may include duplicates; deduplication is the caller's responsibility.

### `check_goedel_health`

Verify the server is reachable and the configured model is loaded. Useful as a precondition before a proof session.

## Setup

### 1. Prerequisites

- LM Studio running with server on `localhost:1234`
- Goedel-Prover-V2-32B loaded (any quant; `mlx-community/Goedel-Prover-V2-32B-8bit` recommended for Apple Silicon)
- `uv` installed (`brew install uv` if needed)

Load Goedel in LM Studio:

```bash
lms load mlx-community/Goedel-Prover-V2-32B-8bit --identifier goedel-prover-v2-32b --ttl 0
lms ps   # verify it's loaded with the right identifier
```

The identifier must match `GOEDEL_MODEL_ID` (default `goedel-prover-v2-32b`).

### 2. Register the MCP server with Claude Code

Add to `.mcp.json` in your project root, or to `~/.claude/mcp.json` globally:

```json
{
  "mcpServers": {
    "goedel": {
      "command": "/Users/mvid/Development/reliq/colosseum/mcp/goedel-mcp/goedel_mcp.py"
    }
  }
}
```

The script uses `uv run --script` with inline dependency metadata, so no separate install step is needed. First invocation downloads dependencies into a uv-managed environment.

### 3. Verify

In a Claude Code session after registration:

```
mcp__goedel__check_goedel_health()
```

Expected output: `{ok: true, model_loaded: true, completion_ok: true, ...}`.

## Configuration

Environment variables (defaults shown):

| Var | Default | Purpose |
|-----|---------|---------|
| `GOEDEL_LMSTUDIO_URL` | `http://localhost:1234/v1` | LM Studio OpenAI-compatible base URL |
| `GOEDEL_MODEL_ID` | `goedel-prover-v2-32b` | Model identifier as loaded in LM Studio |
| `GOEDEL_TIMEOUT_S` | `180` | Per-request timeout in seconds |

Override in the `.mcp.json` entry:

```json
{
  "mcpServers": {
    "goedel": {
      "command": "/path/to/goedel_mcp.py",
      "env": {
        "GOEDEL_MODEL_ID": "custom-identifier",
        "GOEDEL_TIMEOUT_S": "300"
      }
    }
  }
}
```

## Typical usage pattern

The intended composition pattern in Claude Code, given lean-lsp-mcp is also registered:

1. Claude reads the current Lean goal via `lean_goal` (lean-lsp-mcp)
2. Claude calls `propose_lean_tactic(goal_state, n=5)` (goedel-mcp)
3. Claude tests each candidate via `lean_multi_attempt` (lean-lsp-mcp)
4. Claude commits the first candidate that closes or advances the goal
5. On failure across all candidates: backtrack, decompose, or escalate

This is "Claude orchestrates, Goedel proposes, Lean verifies" — the three-specialist pipeline the Colosseum methodology calls for at the proof layer.

## Status

**v0.1** — Initial implementation, untested end-to-end against a real proof session. Known gaps:

- Goedel's exact training-time prompt format is not publicly specified; the current prompt template is reasonable but may be suboptimal. Tune empirically once a real proof workload exists.
- No deduplication or ranking of candidates. Claude can do this; eventually worth a built-in heuristic.
- No structured parsing of multi-tactic responses (e.g., a sequence of tactics in one generation). Single tactic per candidate for now.
- No streaming. Each candidate is a full completion roundtrip.

## Future work

- `propose_proof_sketch` tool — ask Goedel for a multi-step proof scaffold, not just one tactic
- `verify_tactic` tool — integrate lean-lsp-mcp's `lean_multi_attempt` directly so the MCP returns only candidates that compile
- Candidate ranking by log-prob (if LM Studio exposes it)
- Cache: identical goal_state + temperature 0 should return cached candidates
