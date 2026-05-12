# quint-mcp

MCP server wrapping [Quint](https://github.com/informalsystems/quint) — Informal Systems' specification language for protocols and state machines — as a Claude-callable tool. Quint sits on the **spec axis** of the Colosseum pyramid: it captures protocol structure before any Rust is written, and exposes invariants and temporal properties that Apalache can model-check.

## Pipeline

```
.qnt spec ──typecheck──► validated
          ──run (random simulation)──► statistical confidence on traces
          ──verify (Apalache)──► symbolic model check up to N steps
```

`typecheck` is the cheap-fast lint. `run` randomly explores traces and reports invariant violations statistically. `verify` invokes Apalache for symbolic exhaustive checking up to a bounded depth — slower but produces real proofs (within the bound).

## Tools

### `check_quint_health`

Verify the `quint` binary is installed and runnable. Reports version. Apalache is auto-downloaded by quint on first `verify` call.

### `list_quint_specs(path)`

Walk a `.qnt` file or directory and inventory the structural surface: module names, invariant declarations (heuristic — names starting with `inv_`, `safety_`, `temporal_` or ending in `_inv` / `_invariant` / `_safety` / `_live`), action names, assume blocks.

Useful for orientation before any verify call.

### `typecheck_quint(spec_path, extra_args?, timeout_s?)`

Run `quint typecheck`. Fastest pass — catches syntax and type errors.

### `run_quint(spec_path, invariant?, main?, max_steps?, max_samples?, seed?, extra_args?, timeout_s?)`

Run `quint run`. Random / symbolic simulation. Optionally check an invariant.

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `spec_path` | string | — | Absolute path to .qnt file |
| `invariant` | string? | null | Comma-separated invariant names |
| `main` | string? | null | Main module (default: filename stem) |
| `max_steps` | int? | 10 | Steps per trace |
| `max_samples` | int? | 10000 | Independent traces sampled |
| `seed` | string? | null | Random seed for reproducibility |
| `timeout_s` | float? | 600 | |

Returns raw stdout/stderr plus a parsed `summary` (verdict, sample count, violated invariant name if any).

### `verify_quint(spec_path, invariant?, invariants?, inductive_invariant?, main?, max_steps?, extra_args?, timeout_s?)`

Run `quint verify` (Apalache). Symbolic exhaustive checking. Apalache requires JVM 17+ — quint auto-downloads it to `~/.quint/apalache` on first call.

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `spec_path` | string | — | Absolute path to .qnt file |
| `invariant` | string? | null | Comma-separated invariant names |
| `invariants` | list? | null | Per-invariant violation reporting |
| `inductive_invariant` | string? | null | Inductive invariant (no step bound) |
| `main` | string? | null | Main module |
| `max_steps` | int? | (quint default 10) | Symbolic depth |
| `timeout_s` | float? | 600 | Apalache can be slow |

Returns raw output plus a parsed `summary` (verdict ∈ {ok, violation, unknown}, list of violated invariants, counterexample file path if produced).

## Setup

### 1. Install Quint

```bash
npm install -g @informalsystems/quint
quint --version
```

Verified working with **quint 0.32.0** on this machine.

### 2. Apalache (auto-downloaded)

`quint verify` downloads Apalache automatically to `~/.quint/apalache` on first run. Requires:

- JVM 17+ on PATH (`java -version`)
- ~250 MB of disk
- Internet for the first download

If verify hangs the first time, run it manually once outside Claude Code to let the download complete.

### 3. Register with Claude Code

```json
{
  "mcpServers": {
    "quint": {
      "command": "/Users/mvid/Development/reliq/colosseum/mcp/quint-mcp/quint_mcp.py"
    }
  }
}
```

Override the binary location if quint is not on the default PATH:

```json
{
  "env": {
    "QUINT_BIN": "/abs/path/to/quint"
  }
}
```

### 4. Verify

```
mcp__quint__check_quint_health()
```

Expected: `ok: true` with a version string.

## Configuration

| Var | Default | Purpose |
|-----|---------|---------|
| `QUINT_BIN` | `quint` | Binary location |
| `QUINT_TIMEOUT_S` | `600` | Default per-call timeout |
| `QUINT_MAX_STEPS` | `10` | Default trace length for `run` |
| `QUINT_MAX_SAMPLES` | `10000` | Default samples for `run` |

## Typical usage pattern

In a Colosseum verification session, Quint usage comes **upstream of code**:

1. Claude calls `check_quint_health()`
2. Claude reads the intent document; if the system has protocol/temporal properties, drafts a `.qnt` spec
3. Claude calls `list_quint_specs(specs_dir)` to inventory what already exists (or what was just drafted)
4. Claude calls `typecheck_quint(spec_path)` — fail fast on syntax
5. Claude calls `run_quint(spec_path, invariant=...)` — cheap reality check
6. Claude calls `verify_quint(spec_path, invariants=[...])` — symbolic model check
7. On `violation`: route to `colosseum-failure-classifier` with the counterexample file. Likely `spec_wrong`, `code_wrong` (if Rust exists yet), or `state_space_blowup` if Apalache exhausted.
8. On `unknown`: typically `state_space_blowup` — simplify the spec, not the bound

Quint's role in the pyramid: it catches protocol bugs at the architecture stage, before any Rust is written. Bugs found here cost a spec edit; the same bugs found at the Verus or Kani layer cost a code + spec edit; found in production, they cost an incident.

## Status

**v0.1** — Discovery + typecheck + run + verify wrappers. Validated on Quartz's existing `attestation.qnt` and `handshake.qnt` specs (2 specs with 20+ invariants).

Known gaps:

- `list_quint_specs` invariant detection is heuristic (name-pattern based). Quint has no syntactic distinction between an invariant and any other `val` — convention is the only signal. Specs that don't follow `inv_` / `_invariant` naming will under-report.
- No counterexample parsing yet. When Apalache produces an `out.itf.json`, the path is surfaced but the trace itself is not parsed into a structured form.
- No incremental verification cache. Each `verify_quint` call re-runs Apalache.

## Future work

- Parse `.itf.json` counterexamples into a structured trace summary so the classifier can route without re-reading the file
- Subcommand for `quint compile` (Quint → TLA+ for users who want the TLA+ output)
- A `find_invariant_violations` helper that runs all heuristically-detected invariants against a spec in one call
