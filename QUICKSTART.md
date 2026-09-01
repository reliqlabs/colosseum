# Quickstart: a new project, the Colosseum way

This is the front door. You have an idea for a piece of software and want to build it under this methodology. The sequence below is the whole journey; each step names the document or skill that owns the details. Vocabulary is in [CONCEPTS.md](./CONCEPTS.md), concepts and rationale in [README.md](./README.md), full tool setup in [INSTALL.md](./INSTALL.md).

## 0. Install the minimum stack

You do not need everything in INSTALL.md on day one. The minimum to start:

1. Rust, Python 3.11+ with `uv`, and either Claude Code or OMP (INSTALL §1)
2. Clone this repo (INSTALL §2)
3. Install the skills and agents for the selected harness (INSTALL §9)

Add the rest when the workflow first calls for it:

- Quint + JVM (INSTALL §3.1, §1.3) when you reach stage 4 and your system has protocol or state-machine semantics
- Kani (INSTALL §4.1) when you reach stage 8 with real Rust
- OpenCode CLI + providers (INSTALL §7) before using the calibrated reference or compatibility dispatch path; OMP-native fan-out does not require OpenCode
- Verus, Aeneas, Lean (INSTALL §4.2 through §4.5) when the verification pyramid's upper layers come into play

Each MCP's health check reports gracefully when its tool is missing, so a partial install never blocks the layers you do have.

## 1. Set up the project directory

For OMP, the initializer installs project-local agents, all Colosseum skills,
the six MCP definitions, and the evidence directory. An `--harness omp` scaffold
is OMP-only: it ships no `.opencode/` agents or `opencode_dispatch.py` (use
`--harness claude-code` for the OpenCode reference transport):

```bash
export COLOSSEUM=/absolute/path/to/colosseum
colosseum/scripts/colosseum_init.py <project> --harness omp
```

The generated `.omp/mcp.json` references `COLOSSEUM`. Export it before starting
OMP, plus `VERUS_BIN`, `CHARON_BIN`, and `AENEAS_BIN` when those optional layers
are installed. The initializer preserves unrelated MCP servers and only replaces
conflicting Colosseum entries when passed `--force`.

For Claude Code, omit `--harness omp` and follow INSTALL §9 for the user-level
skill and agent links.

`.colosseum/` holds every methodology artifact the project produces: the intent,
trust ledger, adversarial reports, and verification runs. The canonical layout
is in CONCEPTS.md under "Project layout".

## 2. Walk the ten stages

Each stage produces an artifact that anchors the next. Claude Code exposes the
skills as `/colosseum-*`; OMP exposes them as `/skill:colosseum-*`.

1. **Intent.** Run `/colosseum-intent` in Claude Code or `/skill:colosseum-intent` in OMP for a new system. For existing code, run `/colosseum-reverse-intent` in Claude Code or `/skill:colosseum-reverse-intent` in OMP. Produces `.colosseum/intent.md`, the human-anchored source of truth. Do not skip sections; everything downstream is bounded by this document's quality.
2. **Tracer prototype.** Fast, ugly, throwaway Rust that proves the design is feasible. Apply the discard gates from README stage 2 before promoting or discarding it.
3. **Intent v2.** Fold what the tracer taught you back into the intent.
4. **System spec.** Quint or TLA+, only if distributed or concurrent semantics matter. Skip explicitly otherwise.
5. **Implementation spec.** Lean specs and/or Verus annotations derived from the intent. For crypto-touching code, build on VCV-io rather than axiomatic stubs (INSTALL §4.5).
6. **Adversarial spec review.** Run `/colosseum-adversarial` in Claude Code or `/skill:colosseum-adversarial` in OMP. Single-voice is for routine drafts; use an explicit multi-family subset or the canonical 4-voice profile for milestones. Reports persist verbatim under `.colosseum/attacks/`. Revise and re-attack until the spec survives.
7. **Implementation.** Rust against the validated specs. Pure cores, narrow effects, explicit state.
8. **Verification.** Run `/colosseum-verify` in Claude Code or `/skill:colosseum-verify` in OMP continuously. The pyramid routes each property to the cheapest tool that can check it. Run `/colosseum-code-adversarial` in Claude Code or `/skill:colosseum-code-adversarial` in OMP here to read the implementation against the intent.
9. **Failure classification.** When verification fails, dispatch the `colosseum-failure-classifier` agent: spec wrong, code wrong, prover stuck, tool mismatch, state-space blowup, or infrastructure — `INDETERMINATE` when the evidence cannot decide. Route the fix accordingly.
10. **Coverage dashboard.** Run `scripts/coverage_dashboard.py` over typed G1 evidence for per-claim status. Run `/colosseum-compose` in Claude Code or `/skill:colosseum-compose` in OMP to maintain `.colosseum/ledger.md`. The initializer installs `check_ledger_references.py` and `check_evidence_records.py` under `.colosseum/scripts/`; wire both into CI so reference drift and stale or incomplete evidence fail loudly.

After the project is spec'd, every later change goes through `/colosseum-change` in Claude Code or `/skill:colosseum-change` in OMP. It triages whether the change touches intent and walks the upstream-first revision sequence.

## 3. The first adversarial pass, concretely

When you reach stage 6 for the first time:

1. Initialize the project for your harness. In OMP, confirm the generated
   `omp_native` model patterns in `/model`. Complete INSTALL §7 only when using
   OpenCode.
2. Edit `<project>/.colosseum/dispatch.json`: set `project_root`, `target_spec`,
   and the slice plan. OMP-native routes are generated from the registry.
   OpenCode voice entries remain project-editable.
3. Run `/skill:colosseum-adversarial` in OMP or
   `/colosseum-adversarial` in Claude Code. OMP uses its native agent fan-out by
   default when every selected route is reachable. OpenCode is the calibrated
   reference and explicit compatibility transport; dispatch never falls back
   between transports silently.

All OMP-native routes are currently calibration-pending. Label their reports
uncalibrated. Cloud voices bill per token, so routine work defaults to one voice;
reserve multi-family panels for changes that justify the cost.

## What done looks like

A mature Colosseum project has: an intent doc that survived multi-voice attack, specs encoding it, an implementation the pyramid checks on every revision, a ledger whose every trust claim cites live code lines, and a CI gate that fails when any of that drifts. Trust is calibrated to coverage, not to vibes.
