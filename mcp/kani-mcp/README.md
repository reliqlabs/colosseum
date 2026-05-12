# kani-mcp

MCP server wrapping cargo-kani — Rust's bounded model checker — as a Claude-callable tool. Part of the Colosseum v1 verification-pyramid backbone.

Kani sits between property tests and theorem proving on the pyramid: it gives exhaustive guarantees within loop-unwinding bounds, with fast turnaround (seconds-to-minutes per harness). Bugs Kani finds are real counterexamples, not statistical artifacts.

## Tools

### `check_kani_health`

Confirm cargo-kani is installed and reachable. Returns version output. Use as a precondition before any verification run.

### `list_kani_harnesses(crate_path)`

Walk a crate's source tree and discover every `#[kani::proof]`-annotated function. Returns `{name, file, line}` per harness.

### `run_kani_harness(crate_path, harness_name?, unwind?, extra_args?, timeout_s?)`

Run cargo-kani against a crate, optionally targeting a specific harness. Returns full stdout/stderr plus a best-effort structured `summary` (verdict, per-check status, counterexample lines).

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `crate_path` | string | — | Absolute path to the crate root (Cargo.toml dir) |
| `harness_name` | string? | null | Specific harness to run; omit to run all |
| `unwind` | int? | 10 | Loop-unwinding bound |
| `extra_args` | list[string]? | null | Verbatim cargo-kani flags |
| `timeout_s` | float? | 300 | Per-run timeout |

## Setup

### 1. Install cargo-kani

```bash
cargo install --locked kani-verifier
cargo kani setup
```

See <https://model-checking.github.io/kani/install-guide.html> for current install guidance.

### 2. Register with Claude Code

Add to `.mcp.json` in your project root, or to `~/.claude/mcp.json` globally:

```json
{
  "mcpServers": {
    "kani": {
      "command": "/Users/mvid/Development/reliq/colosseum/mcp/kani-mcp/kani_mcp.py"
    }
  }
}
```

The script uses `uv run --script` with inline dependency metadata — no separate install step required.

### 3. Verify

In a Claude Code session:

```
mcp__kani__check_kani_health()
```

Expected: `{ok: true, version_output: "cargo-kani 0.x.y", ...}`.

## Configuration

Environment variables (defaults shown):

| Var | Default | Purpose |
|-----|---------|---------|
| `KANI_BIN` | `cargo` | Binary used (invoked as `<bin> kani ...`) |
| `KANI_DEFAULT_UNWIND` | `10` | Default loop-unwinding bound |
| `KANI_TIMEOUT_S` | `300` | Default per-run timeout in seconds |

## Typical usage pattern

In a Colosseum verification session against a Rust crate:

1. Claude calls `list_kani_harnesses(crate_path)` to inventory the verification surface
2. For each harness, Claude calls `run_kani_harness(crate_path, harness_name)` and inspects `summary.verdict`
3. On `failed` verdicts, Claude pulls the counterexample from stdout and routes to the failure classifier (spec wrong / code wrong / unwind too small)
4. On `successful`, Claude advances to the next layer (Verus, Aeneas/Lean) or commits the harness as verified

Kani's role in the pyramid: fast, bounded, exhaustive within bounds. Cheap layer with surprisingly high yield on edge-case bugs.

## Status

**v0.1** — Initial implementation, untested end-to-end against a real Kani run. Known gaps:

- Output parsing is best-effort regex; cargo-kani's textual format varies across versions and a structured parser is future work
- No structured counterexample extraction (only the "Failed Checks:" line is captured); future work to parse the full trace
- No concurrent-mode flag passthrough (e.g., `--enable-unstable --concrete-playback`); add via `extra_args` for now

## Future work

- Structured counterexample parsing (assignments to symbolic variables, trace steps)
- `run_concrete_playback` tool to replay a failing trace as a deterministic test
- Harness scaffolding tool — given a function signature and an intent clause, propose a `#[kani::proof]` skeleton
- Cache verdicts keyed on (crate hash, harness, unwind) to avoid redundant runs
