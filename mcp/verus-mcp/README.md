# verus-mcp

MCP server wrapping [Verus](https://verus-lang.github.io/verus/) — SMT-backed verification for Rust — as a Claude-callable tool. Part of the Colosseum v1 verification-pyramid backbone.

Verus sits above Kani on the pyramid: SMT-based (Z3), more expressive than bounded model checking, faster than full theorem proving. Annotations (`requires`, `ensures`, `invariant`, `spec`, `decreases`) are discharged automatically when they fit Z3's reach.

## Tools

### `check_verus_health`

Verify Verus is installed and runnable. Returns version output or an install hint.

### `list_verus_annotations(path)`

Inventory Verus markers (`spec fn`, `proof fn`, `requires`, `ensures`, `invariant`, `verus!` blocks, `#[verifier(...)]`) in a file or directory tree. Useful for discovering the verification surface of a crate.

### `verify_verus_file(file_path, extra_args?, timeout_s?)`

Run Verus against a single `.rs` file. Returns full stdout/stderr plus a parsed `summary` (verdict + verified/error counts + error locations).

### `verify_verus_crate(crate_path, extra_args?, timeout_s?)`

Run Verus against a Rust crate. Prefers `cargo verus` integration; falls back to running `verus` directly against `src/lib.rs` or `src/main.rs` when the cargo subcommand is unavailable.

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `file_path` / `crate_path` | string | — | Absolute path |
| `extra_args` | list[string]? | null | Verbatim CLI flags |
| `timeout_s` | float? | 300 | Per-run timeout |

## Setup

### 1. Install Verus

Verus is not on crates.io; install from source per the [official guide](https://verus-lang.github.io/verus/guide/install.html). Briefly:

```bash
git clone https://github.com/verus-lang/verus.git
cd verus/source
./tools/get-z3.sh   # downloads pinned Z3
source ../tools/activate
vargo build --release
# add verus/source/target-verus/release to PATH
```

Verify:

```bash
verus --version
```

### 2. Register with Claude Code

Add to `.mcp.json`:

```json
{
  "mcpServers": {
    "verus": {
      "command": "/Users/you/path/to/colosseum/mcp/verus-mcp/verus_mcp.py"
    }
  }
}
```

If `verus` is not on PATH, point at the absolute binary:

```json
{
  "mcpServers": {
    "verus": {
      "command": "/Users/you/path/to/colosseum/mcp/verus-mcp/verus_mcp.py",
      "env": {
        "VERUS_BIN": "/abs/path/to/verus"
      }
    }
  }
}
```

### 3. Verify

```
mcp__verus__check_verus_health()
```

Expected: `{ok: true, version_output: "verus 0.x.y", ...}`.

## Configuration

| Var | Default | Purpose |
|-----|---------|---------|
| `VERUS_BIN` | `verus` | Verus binary location |
| `VERUS_TIMEOUT_S` | `300` | Default per-run timeout |

## Typical usage pattern

In a Colosseum verification session against a Rust crate:

1. Claude calls `list_verus_annotations(crate_path)` to inventory the verification surface
2. For each annotated entry point, Claude calls `verify_verus_file` or `verify_verus_crate`
3. On `failed` verdicts, Claude inspects `summary.error_locations` and routes the failure to `colosseum-failure-classifier`
4. On `successful`, Claude advances to the next layer (Aeneas/Lean for properties Verus could not discharge) or commits

Verus's role in the pyramid: SMT-tractable properties get answered in seconds-to-minutes with no manual proof construction. Properties that require induction, complex quantifier reasoning, or full theorem proving fall through to Aeneas/Lean.

## Status

**v0.1** — Initial implementation, untested end-to-end (Verus install not verified on this machine).

Known gaps:

- Output parsing matches recent Verus output shapes; older Verus versions may report differently. Raw stdout/stderr always available as fallback.
- No structured trigger/precondition diagnostics from Z3's UNSAT cores
- No incremental / cached verification — each call is a fresh run

## Future work

- `propose_verus_annotations` tool — given a Rust function and intent clause, suggest a starter `requires`/`ensures` skeleton
- Structured Z3 UNSAT-core extraction when verification fails
- Triggers-and-quantifier-instantiation diagnostics for spec-stuck cases
- Cache verdicts by (file hash, args) for fast re-verification
