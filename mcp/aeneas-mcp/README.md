# aeneas-mcp

MCP server wrapping [Aeneas](https://github.com/AeneasVerif/aeneas) — the Rust → Lean 4 extraction toolchain — as a Claude-callable tool. The bridge between Colosseum's Rust code layer and its theorem-proving layer (Lean + Goedel).

## Pipeline

```
Rust crate  ──charon──►  LLBC  ──aeneas──►  Lean 4
```

`charon` is the frontend: it parses Rust and produces LLBC (Low-Level Borrow Calculus). `aeneas` is the backend: it translates LLBC into pure Lean 4 (or Coq / F* / HOL4).

Aeneas works on a *functional subset* of Rust — no raw pointers, restricted unsafe, no async (in current configurations). Code targeted for Aeneas extraction must be designed to fit this subset; this is a constraint to plan for, not a deal-breaker.

## Tools

### `check_aeneas_health`

Verify both `charon` and `aeneas` binaries are installed and runnable. Reports presence + version for each.

### `run_charon(crate_path, output_path?, extra_args?, timeout_s?)`

Run charon alone to produce LLBC from a Rust crate. Useful for inspecting the intermediate representation or for incremental workflows that don't always re-extract Lean.

### `extract_rust_to_lean(crate_path, output_dir, backend?, extra_charon_args?, extra_aeneas_args?, timeout_s?)`

Run the full pipeline. Produces `.lean` files (or `.v` / `.fst` / `.sml` depending on `backend`) in `output_dir`. Returns per-stage result so partial failures are diagnosable.

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `crate_path` | string | — | Absolute path to the crate root |
| `output_dir` | string | — | Where extraction outputs go (created if absent) |
| `backend` | string? | `lean` | One of `lean`, `coq`, `fstar`, `hol4` |
| `extra_charon_args` | list? | null | Verbatim charon flags |
| `extra_aeneas_args` | list? | null | Verbatim aeneas flags |
| `timeout_s` | float? | 600 | Per-stage timeout |

### `list_extracted_definitions(output_dir)`

Walk an extracted-Lean directory and report every top-level declaration (`def`, `theorem`, `lemma`, `structure`, `inductive`, `class`, `instance`, `abbrev`). Useful for navigating Aeneas's output and locating which Rust functions became which Lean definitions.

## Setup

### 1. Install Aeneas and charon

Both are built from source. See [https://github.com/AeneasVerif/aeneas](https://github.com/AeneasVerif/aeneas) for current instructions. Briefly:

```bash
# charon
git clone https://github.com/AeneasVerif/charon.git
cd charon && make && export PATH="$PWD/bin:$PATH"

# aeneas
cd ..
git clone https://github.com/AeneasVerif/aeneas.git
cd aeneas && make && export PATH="$PWD/bin:$PATH"
```

Confirm both are on PATH:

```bash
charon --version
aeneas --version
```

### 2. Register with Claude Code

```json
{
  "mcpServers": {
    "aeneas": {
      "command": "/Users/mvid/Development/reliq/colosseum/mcp/aeneas-mcp/aeneas_mcp.py"
    }
  }
}
```

Override binary locations if they're not on PATH:

```json
{
  "mcpServers": {
    "aeneas": {
      "command": "/path/to/aeneas_mcp.py",
      "env": {
        "CHARON_BIN": "/abs/path/to/charon",
        "AENEAS_BIN": "/abs/path/to/aeneas"
      }
    }
  }
}
```

### 3. Verify

```
mcp__aeneas__check_aeneas_health()
```

Expected: both `charon.present: true` and `aeneas.present: true`, with `ok: true` overall.

## Configuration

| Var | Default | Purpose |
|-----|---------|---------|
| `CHARON_BIN` | `charon` | charon binary location |
| `AENEAS_BIN` | `aeneas` | aeneas binary location |
| `AENEAS_BACKEND` | `lean` | Default extraction backend |
| `AENEAS_TIMEOUT_S` | `600` | Default per-stage timeout |

## Typical usage pattern

In a Colosseum verification session targeting the theorem-proving layer:

1. Claude calls `check_aeneas_health()` to confirm the toolchain is available
2. Claude calls `extract_rust_to_lean(crate_path, output_dir)` and inspects the stage-by-stage result
3. If extraction fails: route to `colosseum-failure-classifier` — likely `tool_mismatch` (Rust pattern not supported) or `infrastructure`
4. If extraction succeeds: Claude calls `list_extracted_definitions(output_dir)` to inventory the Lean surface
5. For each extracted theorem with a `sorry`, Claude orchestrates the proof: reads goal via `lean-lsp-mcp`, proposes tactics via `goedel-mcp`, verifies via `lean-lsp-mcp`

Aeneas's role in the pyramid: the only path from real Rust code to deep theorem-proving guarantees. Where Verus and Kani can't reach (induction, complex quantifier reasoning, refinement against abstract specs), Aeneas + Lean takes over.

## Status

**v0.1** — Initial implementation, untested end-to-end (Aeneas install not verified on this machine).

Known gaps:

- Aeneas's CLI shape has evolved across versions; the exact flags this wrapper uses (`-lean`, `-dest`) match recent releases. Older versions may differ — raw command and output are always exposed for debugging.
- No incremental extraction caching. Each `extract_rust_to_lean` call re-runs the full pipeline.
- No structured error parsing for charon/aeneas failures. Raw stderr is returned; failure-classifier subagent handles interpretation.
- The `list_extracted_definitions` regex is conservative — heavily-attributed declarations (`@[simp, …]`) and multi-line declarations may be missed.

## Future work

- Incremental extraction — skip stages when source has not changed
- Charon-level introspection: `inspect_llbc(llbc_path)` to summarize what charon produced before aeneas runs
- Reverse mapping: `find_rust_for_lean_definition(lean_name, output_dir)` so failure-classifier can route Lean proof failures back to specific Rust source
- Proof-obligation enumeration: list every `sorry` in the extracted output so the proof orchestrator knows what work is outstanding
