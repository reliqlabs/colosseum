# Quickstart: a new project, the Colosseum way

This is the front door. You have an idea for a piece of software and want to build it under this methodology. The sequence below is the whole journey; each step names the document or skill that owns the details. Vocabulary is in [CONCEPTS.md](./CONCEPTS.md), concepts and rationale in [README.md](./README.md), full tool setup in [INSTALL.md](./INSTALL.md).

## 0. Install the minimum stack

You do not need everything in INSTALL.md on day one. The minimum to start:

1. Rust, Python 3.11+ with `uv`, and Claude Code (INSTALL §1)
2. Clone this repo (INSTALL §2)
3. Symlink the skills and agents into Claude Code (INSTALL §10)

Add the rest when the workflow first calls for it:

- Quint + JVM (INSTALL §3.1, §1.3) when you reach stage 4 and your system has protocol or state-machine semantics
- Kani (INSTALL §4.1) when you reach stage 8 with real Rust
- OpenCode CLI + providers (INSTALL §7) before your first multi-voice adversarial pass
- Verus, Aeneas, Lean (INSTALL §4.2 through §4.5) when the verification pyramid's upper layers come into play

Each MCP's health check reports gracefully when its tool is missing, so a partial install never blocks the layers you do have.

## 1. Set up the project directory

```bash
mkdir -p <project>/.colosseum/{attacks,changes,verify,scripts}
cp colosseum/scripts/opencode_dispatch.py        <project>/.colosseum/scripts/
cp colosseum/scripts/check_ledger_citations.py   <project>/.colosseum/scripts/
cp colosseum/scripts/dispatch.config.example.json <project>/.colosseum/dispatch.json   # then edit
colosseum/scripts/install-agents.py install --harness opencode --target <project>/.opencode/agent/
```

`.colosseum/` holds every methodology artifact the project produces: the intent, the trust ledger, adversarial reports, verification runs. It is the project's evidence base. The canonical layout is in CONCEPTS.md under "Project layout".

## 2. Walk the ten stages

Each stage produces an artifact that anchors the next. The skill names are Claude Code slash-commands once symlinked.

1. **Intent.** Run `/colosseum-intent` (new system) or `/colosseum-reverse-intent` (existing code). Produces `.colosseum/intent.md`, the human-anchored source of truth. Do not skip sections; everything downstream is bounded by this document's quality.
2. **Tracer prototype.** Fast, ugly, throwaway Rust that proves the design is feasible. Apply the discard gates from README stage 2 before promoting or discarding it.
3. **Intent v2.** Fold what the tracer taught you back into the intent.
4. **System spec.** Quint or TLA+, only if distributed or concurrent semantics matter. Skip explicitly otherwise.
5. **Implementation spec.** Lean specs and/or Verus annotations derived from the intent. For crypto-touching code, build on VCV-io rather than axiomatic stubs (INSTALL §4.5).
6. **Adversarial spec review.** Run `/colosseum-adversarial`. Single-voice (Claude) for routine drafts; the canonical 5-voice panel for milestones. Reports persist verbatim under `.colosseum/attacks/`. Revise and re-attack until the spec survives.
7. **Implementation.** Rust against the validated specs. Pure cores, narrow effects, explicit state.
8. **Verification.** Run `/colosseum-verify` continuously. The pyramid routes each property to the cheapest tool that can check it. Run `/colosseum-code-adversarial` here to read the implementation against the intent.
9. **Failure classification.** When verification fails, dispatch the `colosseum-failure-classifier` agent: spec wrong, code wrong, prover stuck, tool mismatch, or infrastructure. Route the fix accordingly.
10. **Trust ledger.** Run `/colosseum-compose` to maintain `.colosseum/ledger.md`: composition theorems, axiom inventory, code-line citations. Wire `check_ledger_citations.py` into CI so the ledger fails loudly when it drifts from code.

After the project is spec'd, every later change goes through `/colosseum-change`, which triages whether the change touches intent and walks the upstream-first revision sequence.

## 3. The first adversarial pass, concretely

When you reach stage 6 for the first time:

1. Complete INSTALL §7 (OpenCode CLI + providers) if you have not.
2. Edit `<project>/.colosseum/dispatch.json`: set `project_root`, `target_spec`, your slice plan, and the voice roster. The canonical panel is in `skills/colosseum-adversarial/SKILL.md` Step 1.
3. Run `/colosseum-adversarial` in Claude Code. It dispatches the Claude voice in-harness and the non-Claude voices through the project's dispatch script, then synthesizes overlap and divergence across the reports.

Costs are real: cloud voices bill per token. Default to Claude plus one local voice for routine work and reserve the full panel for spec milestones.

## What done looks like

A mature Colosseum project has: an intent doc that survived multi-voice attack, specs encoding it, an implementation the pyramid checks on every revision, a ledger whose every trust claim cites live code lines, and a CI gate that fails when any of that drifts. Trust is calibrated to coverage, not to vibes.
