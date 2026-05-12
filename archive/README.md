# Archive — Colosseum development record

Snapshot of the Claude Code transcripts and auto-memory files captured at the
moment of the `crucible/` → `colosseum/` directory rename (2026-05-12).

## Why this is here

Colosseum was built over multiple Claude Code sessions across a few weeks. The
methodology, MCP wrappers, agent definitions, skills, and first dogfooding
runs all happened inside conversations whose full records live as JSONL
transcripts under `~/.claude/projects/-Users-mvid/`. Memory files under the
same path persisted user/project/feedback context across sessions.

Both are useful as historical record: when a future reader asks "why is the
spec adversary calibrated this way?" or "what failure modes did the local
adversarial layer surface?", the transcripts and memories are the answer.
They are kept here so the project remains self-contained.

## transcripts/

One `*.jsonl` per Claude Code session that touched this work. Each file is a
chronologically-ordered list of user messages, assistant responses, tool
calls, and tool results. They can be replayed manually or parsed for
structured analysis.

| File | Approx role |
|------|-------------|
| `bd0ffebe-…` | Early exploration |
| `244022db-…` | Pre-methodology context (Quartz / verified-cosmwasm groundwork) |
| `1e45b972-…` | Earlier conversation, project-adjacent |
| `4942b5d5-…` | Bridge session |
| `58c6368a-…` | **The main build session — methodology design, MCP construction, agent definitions, skills, first dogfood pyramid run, Allium evaluation, multi-model adversarial dogfood, methodology meta-findings.** (~3.6 MB — the bulk of the project history.) |

## memory/

Snapshot of the auto-memory files at rename time. The live copies remain at
`~/.claude/projects/-Users-mvid/memory/` and are loaded by Claude Code at
every session start. This snapshot is a frozen historical record.

| File | Type | Summary |
|------|------|---------|
| `MEMORY.md` | index | Pointers into the memory store |
| `user_hardware.md` | user | M5 Max MBP, 107 GB unified memory |
| `user_local_inference.md` | user | Runs local LLMs at model-max context |
| `feedback_local_model_speed.md` | feedback | Prefers fast MoE over slow dense |
| `project_reliq_colosseum.md` | project | Layered FV methodology project context |
| `project_colosseum_gaps.md` | project | v0.1 gaps surfaced by Quartz dogfooding |

## Relationship to the live copies

The transcripts and memory files in `~/.claude/projects/-Users-mvid/` remain
the authoritative live copies. Claude Code reads memories from there at
session start, and uses transcripts internally for compaction and replay.

**These archive copies are read-only history.** Updating live memory from this
snapshot is not recommended — the live copies will have diverged since rename
time. Treat this directory as a museum, not as a working directory.
