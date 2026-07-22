# OMP-native fan-out E2E smoke — 2026-07-22

**Scope: single-voice transport smoke, NOT canonical-panel calibration.** This
records one true project-rooted end-to-end run of the OMP-native adversarial
fan-out (`skills/colosseum-adversarial/omp_fanout.py`) through the installed
`.omp/agents/colosseum-spec-adversary` wrapper. It proves the transport seam and
the fail-closed session-root gate work against a real, separate OMP session. It
does **not** validate the canonical 4-voice route (that needs external provider
credentials + cost) and carries no recall/calibration claim — the voice remains
`calibration:pending`.

## Setup

- Clean project scaffolded with `scripts/colosseum_init.py <proj> --harness omp
  --target-spec <proj>/intent.md`; `intent.md` a trivial `double(n:u32)->2n` spec.
- `.colosseum/dispatch.json` `omp_native` rewritten to a single available voice
  (`claude-local`, `anthropic/claude-opus-4-8`, `calibration:pending`) with a
  recomputed `route_hash` (`sha256:6b2d2ef4ba1eb493`), validated by
  `load_omp_native_config`. The shipped canonical 4 voices were not used
  (external creds/cost).
- Project preflight scanned clean (empty) — confirming the BEGIN-armor scanner
  fix (commit `4a85223`) unblocks scaffolded projects that ship
  `opencode_dispatch.py` / `omp_fanout.py`.

## Run

```
cd <proj>
omp -p --auto-approve --cwd=<proj> --model=opus "<run fanout eval cell>"
```

Per the persisted session transcript, the executed eval cell ran
`exec(read('/Users/mvid/.claude/skills/colosseum-adversarial/omp_fanout.py'), ns)`
(no `skill://` appears in the transcript), then
`load_omp_native_config(".colosseum/dispatch.json")` and `run_omp_fanout(...,
allow_unverified_isolation=True)`. That absolute path is a symlink to the repo's
`skills/colosseum-adversarial/`, byte-identical to the committed helper (verified
by `diff`) — so the executed helper WAS the current committed code, loaded via the
global symlink, NOT the project's `.omp/skills/colosseum-adversarial/omp_fanout.py`
copy. The dispatched agent wrapper (`colosseum-spec-adversary`) is resolved from
the session cwd, so it did come from the project's `.omp/agents/`.

- Outer `omp -p` exit code: **0**; wall clock: **137.4s** (voice `elapsed_s` 111.2).
- Nested session was project-rooted (session-header `cwd:/tmp/colo-e2e.U4aM`),
  so the fail-closed gate matched `project_root` and dispatch proceeded.

## Result (from the run's `summary.json`, since deleted with the temp project)

- `verdict`: **COMPLETE**, `voices_ok`: **1/1**, `harness`: `omp-native`,
  `agent`: `colosseum-spec-adversary` (the project's `.omp/agents` wrapper, not built-in scout).
- `isolation`: `{"status":"unverified","session_root":"/private/tmp/colo-e2e.U4aM",
  "session_root_source":"PI_SESSION_FILE session-header cwd"}` — matching root is a
  precondition, not filesystem confinement.
- `preflight.status`: `ok`; `target_spec_sha256`:
  `sha256:e3523f5371b9ef480b63577fabd0483203da9a761272719ecc593302d2b32c24`;
  `target_spec_stable`: true.
- Voice `claude-local`: `status:ok`, `output_bytes:982`, `output_sha256`:
  `sha256:7eed84968b1ab64fbe3cc305806b04811572dd1c78472ec4daaee3f0b8c50383`,
  `prompt_sha256`:
  `sha256:93758506c8bfce6b08415c42a29dd497e0b1c1ad82933255b055c8b50f85fbf7`,
  `agent_id:omp-claude-local`.
- Content hash of the full `summary.json`:
  `sha256:60e31ebf977bf5a97305e068c82c9703377b57fd0836af22a0e4f91592126ccc`.
- The wrapper returned a grounded finding (category
  under-specification/edge-case) on the intent's "on precondition violation:
  behavior is unspecified" clause — i.e. it ran its adversarial contract, not a
  generic reply.

## Cost (observed, from the persisted transcripts)

Summed over every assistant message's `usage.cost.total`, outer and wrapper
separately:

- Outer `omp -p` turn (opus): **$0.8611** (4 assistant messages).
- Wrapper subagent `omp-claude-local` (opus, thinking max): **$0.5667** (3 messages).
- **Total: $1.4278** for one single-voice run. Output tokens ~8,016; input was
  cache-write-dominated (~105k cacheWrite across the two sessions), which is where
  most of the cost sits. This is one anthropic voice; the canonical 4-voice route
  would add three more external-provider wrapper dispatches (not measured here).

## Provenance

The temp project (`/private/tmp/colo-e2e.U4aM`) and its `.colosseum/attacks/`
artifacts were ephemeral and deleted after inspection. The run's OMP session
transcripts persisted on the run host at
`~/.omp/agent/sessions/--private-tmp-colo-e2e.U4aM--/` (main session
`...019f8818-...jsonl` + subagent `.../omp-claude-local.jsonl`), which
independently record the project cwd, model, installed-wrapper dispatch, real
`intent.md` read, and the `COMPLETE 1/1` result. These are machine-local and not
committed.

## What this does not establish

- That the project-installed `.omp/skills/.../omp_fanout.py` copy is the helper
  resolution target: on this host a `~/.claude/skills` symlink to the repo
  shadowed it, so the run validates the committed helper code running
  project-rooted, not the init-installed project copy's load path. (The agent
  wrapper did resolve from the project's `.omp/agents`.)
- Canonical 4-voice-route validation (external providers; creds/cost).
- Any recall/calibration claim (`calibration:pending` unchanged).
- Mechanical filesystem isolation of the subagent (`isolation:unverified`).
