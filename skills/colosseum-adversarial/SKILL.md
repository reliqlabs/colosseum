---
name: colosseum-adversarial
description: Run the Colosseum spec adversary against a specification, single-model or multi-model. Reads the spec and the intent document. Primary dispatch for non-Claude voices is OpenCode CLI (`opencode run --agent spec-adversary --model burnt/<voice>` for gateway-routed frontier voices, or `lmstudio/<local-model-id>` for local voices), orchestrated by the per-project script at `<project>/.colosseum/scripts/opencode_dispatch.py` whose canonical template lives at `colosseum/scripts/opencode_dispatch.py`. The Claude voice runs in-harness via the `colosseum-spec-adversary` Agent subagent. The `external-model-mcp` single-shot calls (`query_gateway` / `query_openai` / `query_google`) and `lm-studio-mcp` `fan_out_local` are NOT the primary dispatch path; they are a fallback used only when OpenCode is not installed on this host. Captures each structured report verbatim under `.colosseum/attacks/`, summarizes overlap and divergence. Includes a separate Quint-adversarial trace-generation step that drives the model checker against named invariants, distinct from intent-adversarial prose critique. Use when a draft spec needs scrutiny before commitment, to re-attack a revised spec after a prior round's findings were addressed, or to mechanically check Quint invariants at milestones.
---

You are orchestrating an adversarial review of a specification. The methodology rests on the claim that *the unit of trust is surviving adversarial scrutiny*, not consensus. Your job is the orchestration: locate the artifacts, dispatch one or more adversaries, capture their output verbatim, persist it, and report overlap + divergence.

You are not the adversary. You do not produce the attacks. You do not soften them. You provide each adversary with everything it needs and stand out of its way.

## Single-voice vs multi-voice

This skill supports two modes:

- **Single-voice (default)** — invoke the `colosseum-spec-adversary` subagent (Claude). Fast, free under the Claude Code subscription, no setup.
- **Multi-voice** — invoke Claude *and* fan the same attack out to non-Claude voices via the OpenCode CLI orchestrator (gateway-routed frontier voices like `burnt/cloudflare-100/@cf/moonshotai/kimi-k2.6` plus local LM Studio voices like `lmstudio/qwen/qwen3.6-27b`). Genuine family diversity, much closer to the methodology's "adversarial beats consensus" claim. Slower; cloud calls cost money.

The user selects via the `voices` parameter (a roster of explicit voice IDs, NOT bucket names — see Step 1 below). Default is `["claude-agent"]`. Recommended for routine spec milestones: `["claude-agent", "lmstudio/<one-loaded-local>"]` (Claude + local floor; free). Recommended for high-stakes spec milestones: 5–7 voices spanning `burnt/` + `lmstudio/` for family diversity (Anthropic / OpenAI-OSS / Moonshot / NVIDIA / Google / Alibaba / Mistral).

**Anti-pattern to avoid.** Do NOT reach for `mcp__external-model__query_gateway` or `mcp__external-model__fan_out_query` as the dispatch path. Those MCP tools exist as a fallback for hosts without OpenCode installed (Step 4 Mode 3 below); they are not the primary dispatch surface. Agents keep defaulting to them because their schemas surface in the harness's deferred-tool list; that is the trap this skill is structured to prevent. Use OpenCode (Mode 1) for every non-Claude voice unless `opencode --version` actually fails on this host.

## Step 1: Locate the artifacts

Ask the user for, or determine from context:

- **Path to the spec under review** — the artifact being attacked. May be a Lean file, Quint module, Verus annotations in a Rust source, a `#[kani::proof]` harness, or any other spec artifact.
- **Path to the intent document** — the human-anchored source of truth the spec is supposed to encode. Check `<project>/.colosseum/intent.md` first (canonical per CONCEPTS.md "Project layout"), then `<project>/intent.md`, then ask.
- **Optional context** — paths to existing tests, related specs, prior attack reports, type signatures, anything that strengthens grounding.
- **Project root** — where `.colosseum/attacks/` should be created. Infer from the spec's location if not given.
- **Voices to dispatch** — a roster of explicit voice IDs, NOT bucket names. Three ID shapes are valid:
  - `claude-agent` — the Claude voice; runs in-harness via the `colosseum-spec-adversary` Agent subagent (Mode 2 below). This is the only voice that does NOT go through OpenCode.
  - `burnt/<gateway-route>` — gateway-routed frontier voice via OpenCode (Mode 1). Current gateway roster (verify against `curl <gateway-base>/models` since the operator's roster drifts): `burnt/cloudflare-100/@cf/moonshotai/kimi-k2.6`, `burnt/cloudflare-100/@cf/nvidia/nemotron-3-120b-a12b`, `burnt/cloudflare-100/@cf/openai/gpt-oss-120b`, `burnt/cloudflare-100/@cf/zai-org/glm-4.7-flash`. Note: the gateway no longer exposes Claude or Gemini routes — use direct `openai/`, `google/`, and in-harness `claude-agent` for those families instead.
  - `lmstudio/<local-model-id>` — local LM Studio voice via OpenCode (Mode 1). Examples: `lmstudio/qwen/qwen3.6-27b`, `lmstudio/google/gemma-4-26b-a4b`, `lmstudio/mistral-small-4-119b-2603`.

  **Canonical 5-voice panel** (the default for non-trivial specs; each voice is the strongest most-recent variant of its family with max thinking enabled, invoked at `--variant max` where supported):
  1. `claude-agent` — Claude Opus 4.x latest (Mode 2 in-harness Agent subagent)
  2. `openai/gpt-5.1-thinking` — ChatGPT latest via OpenCode direct openai provider
  3. `burnt/cloudflare-100/@cf/moonshotai/kimi-k2.6` — Moonshot Kimi K2.6 via OpenCode through the Burnt gateway
  4. `ds4/deepseek-v4-flash` — DeepSeek V4 Flash via OpenCode through the local ds4 provider (DwarfStar4 at `http://127.0.0.1:8000`)
  5. `google/gemini-3-pro` — Gemini latest strongest via OpenCode direct google provider

  For Lean-specific verification work, substitute `lmstudio/leanstral-2603` for one of the general voices; do NOT include Leanstral in general adversarial spec review.

  Smaller routine panels (`["claude-agent", "ds4/deepseek-v4-flash"]` is the cheapest viable multi-voice ensemble — free, two families). Ask the user if not specified for a non-trivial spec — the multi-voice option is load-bearing and should not be silently bypassed.

  Verify the exact `openai/...` and `google/...` model strings against `opencode models openai` and `opencode models google` before dispatch; provider model IDs drift, and the canonical panel above pins names that may need updating to whatever each provider currently exposes as "latest with max thinking".

  **Do NOT accept bucket names** (`"openai"`, `"google"`, `"local"`, `"gateway"`) in the roster. Those names route to the Step 4 Mode 3 single-shot MCP fallbacks, which are not the primary dispatch path. If the user gives you a bucket name, translate it to an explicit voice ID before proceeding.

If either the spec or the intent is missing, stop and ask. An adversary with no intent reference produces vague complaints rather than grounded attacks.

## Step 2: Read and stage

Read both artifacts to confirm they exist and are non-empty. If the intent describes one system and the spec is about another, surface the mismatch before invoking any adversary.

## Step 3: Construct the attack prompt

For non-Claude providers, you must inline everything into a single prompt — they don't have file access. The prompt body is the same for every provider; only the dispatch mechanism differs.

The prompt structure:

```
<system role>
You are a hostile spec reviewer for the Colosseum methodology. Your job is
to find ways the specification under review is wrong, weak, or misleading.

[full body of agents/colosseum-spec-adversary.md system prompt, inlined]
</system role>

<user prompt>
Attack the specification at <SPEC_PATH> against the intent document at <INTENT_PATH>.

=== INTENT DOCUMENT (<INTENT_PATH>) ===
<full text of intent.md>
=== END INTENT DOCUMENT ===

=== SPECIFICATION UNDER REVIEW (<SPEC_PATH>) ===
<full text of spec>
=== END SPECIFICATION ===

[optional: additional context blocks for tests, related specs, prior attack reports]

Report per your system prompt. Severity must be conservative — do not invent
attacks.
</user prompt>
```

The system-prompt portion is read from `agents/colosseum-spec-adversary.md` (strip the YAML frontmatter; use the body text). This ensures every provider operates under identical instructions.

## Step 4: Dispatch the intent-adversarial voices

Dispatch happens in parallel — every requested provider attacks concurrently.

**Three dispatch modes, ordered by preference.** Verified-rcv calibration runs demonstrated that Mode 1 produces strictly better output than Mode 3 for non-trivial specs: more attacks per voice, less hedging, no first-attempt-truncation pattern, and sidesteps the gateway 240s cap structurally. Use Mode 1 as the default; fall back to Mode 3 only when the listed conditions apply.

| Mode | When to use | Key property |
|---|---|---|
| **1. OpenCode + spec-adversary agent (ReAct)** | Default for non-trivial specs (≥ 5K tokens). Required for gateway-prone voices (kimi-k2-6, gpt-oss-120b). Recommended for any voice that supports tool use. | Multi-turn ReAct loop breaks one model invocation into N HTTP requests, each under the gateway's 240s cap. |
| **2. Claude Code Agent subagent** | The Claude voice slot in a multi-model ensemble. | Direct Anthropic API; no gateway hop; no Bug 3 / Bug 4 exposure. |
| **3. Inline single-HTTP-request** | Fallback. Use when (a) spec is small (< 5K tokens) and the ReAct overhead isn't worth paying, (b) the voice is local + tool-use-unfriendly (some older non-tool-trained LM Studio models), or (c) the harness doesn't have OpenCode/ReAct available. | Simpler. Single HTTP request, single response. Exposed to gateway timeout caps. |

**Two orchestration shapes** layered on top of the modes above:

- **In-process** — the running Claude Code session dispatches each voice as a child Agent / MCP call, blocks until all return, then synthesizes. Works when every voice can be invoked from one harness (Mode 2 + Mode 3 inlined MCPs).
- **Harness-agnostic manifest** (`scripts/colosseum_run.py`) — voices live in different harnesses (Claude voice in Claude Code via Mode 2, non-Claude voices in OpenCode via Mode 1). Each harness reads + updates a shared `run.json` manifest; the manifest is the state machine. See `colosseum/scripts/README.md` for the schema, lifecycle, and CLI usage. Required when Mode 1 is in the panel and Claude must remain in-process.

### Mode 1: OpenCode + spec-adversary agent (ReAct) — recommended default

Use the `spec-adversary` OpenCode agent at `colosseum/agents/opencode/spec-adversary.md` (canonical source) → installed via `colosseum/scripts/install-agents.py install --harness opencode --target <project>/.opencode/agent/` into the project's `.opencode/agent/` directory. The agent reads the target spec on demand via OpenCode's Read tool (`permission.read: allow`); the invocation message names a `TARGET_SPEC` path plus an optional `TARGET_SLICE` for per-section dispatch.

**Invocation shape**:

```bash
opencode run --agent spec-adversary --model burnt/cloudflare-100/@cf/moonshotai/kimi-k2.6 \
  --variant max --format default --dangerously-skip-permissions \
  "TARGET_SPEC: /path/to/intent.md\n\nTARGET_SLICE: temporal-invariants — ..."
```

Orchestrate (voice × slice) pairs from a Python script that captures stdout per call and writes per-section files. **Canonical orchestrator: `colosseum/scripts/opencode_dispatch.py`** — copy to `<project>/.colosseum/scripts/opencode_dispatch.py` and supply a project-local config at `<project>/.colosseum/dispatch.json` (voice roster + slice plan + optional context appendix). See `colosseum/scripts/dispatch.config.example.json` for the schema. The verified-rcv project keeps a pinned variant of this script as its in-tree history; the colosseum/ copy is the one new projects should start from.

**Per-voice voice IDs to pass to `--model`** (configured in `~/.config/opencode/opencode.jsonc`; the gateway roster drifts with operator curation, so verify against `curl <gateway-base>/models` before a milestone run):

- `openai/gpt-5.1-thinking` — ChatGPT latest, direct provider (canonical panel voice)
- `google/gemini-3-pro` — Gemini strongest, direct provider (canonical panel voice)
- `ds4/deepseek-v4-flash` — DeepSeek V4 Flash, local DwarfStar4 runner (canonical panel voice)
- `burnt/cloudflare-100/@cf/moonshotai/kimi-k2.6` — Moonshot via gateway (canonical panel voice)
- `burnt/cloudflare-100/@cf/nvidia/nemotron-3-120b-a12b` — NVIDIA Nemotron 3 120B-A12B MoE via gateway; reasoning-on
- `burnt/cloudflare-100/@cf/openai/gpt-oss-120b` — OpenAI-OSS via gateway
- `burnt/google-1/gemini-3.5-flash` — Gemini Flash via gateway; cheap fallback when the direct google provider is not configured (Flash tier, not Pro — direct `google/gemini-3-pro` is the canonical Gemini voice)
- `burnt/cloudflare-100/@cf/zai-org/glm-4.7-flash` — Zhipu (~30B "flash" tier) — **EXCLUDED from gateway adversarial dispatch** per verified-rcv calibration. Exhibited degenerate-loop behavior in both inline dispatch (paragraph repetition during reasoning-budget burnout) and subagent-dispatch parallel runs (enumerated fake attacks #4-75+ on a single slice). At its size class it is local-model-tier, not gateway-frontier-tier. If a Zhipu voice is wanted, use a full (non-flash) glm tier or pull a comparable model into LM Studio
- `lmstudio/<local-model-id>` — any model configured under OpenCode's `lmstudio` provider (matches names in your `lms ls`)

The gateway no longer exposes Anthropic routes; the Claude voice always runs in-harness via Mode 2.

**Required configuration in `opencode.jsonc`**: set `limit.output ≥ 65536` (recommend `131072`) per gateway model so Turn 2's analysis response budget never hits a cap mid-report. With the default 16K cap, thorough reasoning models truncate mid-sentence and the orchestrator's retry loop fires; raising to 64K+ makes that pattern disappear.

**Empirical results (verified-rcv calibration, single-voice sequential, output cap 131072)**:

| Voice | Per-slice wall time | Per-slice output | Retry rate |
|---|---|---|---|
| `kimi-k2-6` (ReAct, single sequential) | 143-371s | 6.8-15.0K chars | ~10% |
| `kimi-k2-6` (inlined, 8K max_tokens) | 125s | 35K chars, truncated at length | n/a (truncated) |

ReAct mode caught **5 attacks on state-invariants** (S5/S6/S9/S10 + Block 6 set-relations); inlined kimi found 1 hedged S5 mention. Committed where inlined hedged.

**Failure mode to expect** (under-budgeted): "first attempt fails, retry succeeds" pattern when output cap is at 16K. The model writes its complete report up to the cap and gets cut off; the orchestrator's retry hits a more concise sampling path. Raising the cap eliminates the retries.

### Mode 2: Claude Code Agent subagent — the Claude voice

Invoke the `colosseum-spec-adversary` subagent (at `colosseum/agents/colosseum-spec-adversary.md`) via the Agent tool. The same canonical body powers it; the Claude Code frontmatter (`tools: Read, Grep, Glob, Bash`) gives it full file-access.

Claude operates with native tool access; the inlined prompt body is supplemental, not the only input. This subagent can re-read files, check related code, run diagnostics. No gateway hop, no Bug 3 / Bug 4 exposure.

This is the canonical Claude voice for multi-model ensembles. Run it via the Agent tool in parallel with the OpenCode voices; results are captured as the Agent tool's returned text.

### Mode 3: Inline single-HTTP-request MCP fallback (use only when Mode 1 is unavailable)

**STOP.** Before reaching for this mode, verify Mode 1 is genuinely unavailable. Conditions that justify Mode 3 are narrow:

1. `opencode --version` fails on this host (CLI not installed).
2. The target spec is small (< 5K tokens) AND the project has no `<project>/.colosseum/scripts/opencode_dispatch.py` AND copying the template from `colosseum/scripts/` would not amortize over future runs.
3. The voice is local + tool-use-unfriendly (older non-tool-trained LM Studio models that fail the ReAct loop).

If you are in this skill and reaching for `mcp__external-model__query_gateway` or `mcp__external-model__fan_out_query` because those tools' schemas are easy to load via ToolSearch, **that is the failure mode this skill exists to prevent**. The deferred-tool list surfaces those MCPs with first-class schemas; OpenCode dispatch requires Bash plus a per-project orchestrator script. The path-of-least-friction is the wrong path. Mode 1 produces strictly better output (verified-rcv calibration: more attacks per voice, less hedging, no truncation, sidesteps gateway timeout caps). Take the friction.

Once you have confirmed Mode 1 is genuinely unavailable per a condition above, the inline channels are:

- **gateway** — call `external-model-mcp`'s `query_gateway(prompt=..., model="<gateway-model-id>")`. The gateway is an operator-curated OpenAI-format multi-model endpoint; available `model` ids drift with operator curation, so list them first via the gateway's `/models` endpoint (current chat-tier set: `cloudflare-100/@cf/moonshotai/kimi-k2.6`, `cloudflare-100/@cf/nvidia/nemotron-3-120b-a12b`, `cloudflare-100/@cf/openai/gpt-oss-120b`, `cloudflare-100/@cf/zai-org/glm-4.7-flash`, `google-1/gemini-2.5-flash`, `google-1/gemini-3.1-flash-lite`, `google-1/gemini-3.5-flash`; no Anthropic routes).
- **local** — call `lm-studio-mcp`'s `fan_out_local` with `models=` set to the user's preferred local pair (default: all loaded). The inlined prompt is the only input — local models have no file access in this mode.
- **openai** — call `external-model-mcp`'s `query_openai(prompt=...)`. The inlined prompt is the only input.
- **google** — call `external-model-mcp`'s `query_google(prompt=...)`.

**Gateway configuration**: the MCP loads `COLOSSEUM_GATEWAY_BASE_URL` + `COLOSSEUM_GATEWAY_API_KEY` + `COLOSSEUM_GATEWAY_DEFAULT_MODEL` from `.env` (gitignored). Search order: `$COLOSSEUM_DOTENV` env override → `CWD/.env` → `<colosseum-repo-root>/.env` → `~/.colosseum.env`. After editing `.env` the MCP process must restart.

**Inline-mode timeout caveats** (do NOT apply to Mode 1, which sidesteps them via ReAct):

- **Gateway-wide ~240s ceiling** (Bug 3). Calibrate `max_tokens` per upstream model's generation speed to fit under it. Empirical values at a ~22K-token prompt: `kimi-k2-6` ≤ 8K (133s); `glm-4-7-flash` ≤ 16K (152s); `gpt-oss-120b` 16K in 47s. Above these, HTTP 408. Truncation at the cap loses the verdict line and most of the latter half of the report.
- **Anthropic-route ~127s ceiling** (Bug 4, Cloudflare 524). Historical: when the gateway carried Anthropic routes, `claude-opus-4-7` and `claude-sonnet-4-6` hit it on long+high-budget inlined dispatches. The gateway no longer exposes Anthropic routes; the Claude voice always runs via **Mode 2** (Agent subagent).

**Parameter quirk**: `claude-opus-4-7` rejects the `temperature` request parameter (HTTP 400). Omit `temperature` when calling that model id. The MCP's `query_gateway` accepts `temperature=None` to opt out.

**Reproducibility discipline**: pin the exact model id + max_tokens + observed elapsed in your dispatch ledger so the timeout shape is reproducible across runs.

(For "openai" and "google" together, you may use `external-model-mcp`'s `fan_out_query(prompt, providers=["openai", "google"])` for one round-trip. The gateway is per-model — there is no fan-out across gateway models in one MCP call.)

### Excluded model classes — theorem-prover specialists

**Do not include theorem-prover specialist models (e.g., `goedel-prover-v2-32b`, ProofGPT-class, math-tactic-tuned models) in adversarial spec review.** These models pattern-match the prompt as a *proof goal* and attempt Lean / Coq tactics rather than treating the spec as a target to *attack*. Verified-rcv calibration included goedel-prover-v2-32b in an 8-voice fan-out and observed 8K tokens of degenerate tautology loops with abstract variable lists — wall time 852 seconds, output unusable. Use these models at the **verify-pyramid layer** instead (proof completion / tactic suggestion via `mcp__goedel__propose_lean_tactic`).

### Cross-session local-model contention (LM Studio ops notes)

When multiple agents work on related projects in parallel, both may invoke `mcp__lm-studio__*` against the same local LM Studio instance. With LM Studio configured for JIT loading + auto-evict-on-different-model (the typical consumer-hardware default), requests from one session can evict the model another session is mid-response on. Symptom: `HTTP 400: {"error":"Model unloaded."}` errors mid-dispatch.

Three discipline items:

1. **Pre-load each model before dispatch** via `lms load <model> --gpu max` (synchronous). Forces the model fully into memory before the chat-completion request fires. The verified-rcv dispatch wrapper at `verified-rcv/.colosseum/scripts/fan_out_dispatch.py` does this via a `lms_load` helper.
2. **Retry-on-unload up to 2 times** in the dispatch wrapper. Catches the race between pre-load and chat-completion that the cross-session contention introduces.
3. **Coordinate cross-session dispatch** when two agents work in parallel: one fan-out at a time across sessions, or accept best-effort with retries. The `colosseum_run.py` manifest protocol gives a natural coordination point — both sessions read + update the same `run.json`.

Wait for all parallel dispatches to complete. Capture each response.

## Step 5: Quint-adversarial trace generation

The intent-adversarial dispatch above operates on the *intent doc* (and optionally on a Lean / Verus / Quint spec read as prose). It produces voice critiques. It does NOT, by itself, drive a model checker against the Quint spec to produce adversarial traces against named properties.

That is a separate step. It uses the Quint spec as an executable artifact, not as a target for prose critique. Run it whenever a Quint spec is the project's protocol model AND any of the following are true:

- A new admin transition has been added to the spec (use `colosseum-lifecycle-adversary` instead — it subsumes this step for multi-tx admin features)
- A new invariant has been added to the spec and has not yet been counterexample-checked
- A code revision has touched a path the Quint spec is supposed to mirror
- The project is at a milestone (release, audit, external review) and Quint coverage was last exercised more than a small number of commits ago

### Procedure

For each Quint invariant named in the spec or in intent §3.2:

1. Run `quint run --invariant <inv_name> --max-steps <N> specs/<file>.qnt` (default `N=10`, escalate to 20 or 30 for invariants whose suspected violation requires longer interleavings).
2. Record the result:
   - **Counterexample found**: capture the trace as a sequence of `(action, args)`. Note the step at which the invariant was first violated.
   - **No counterexample within bound**: record the bound. This is informative — an invariant that holds under bound-10 has been mechanically checked under that bound, but a higher-bound run may produce a counterexample.
   - **Tool error / spec error**: surface the error verbatim. Do not silently move on.
3. For each counterexample, cross-reference to code:
   - **Code enforces the invariant via a check the Quint spec did NOT model.** Spec is under-specified relative to code. Fix the spec (add the precondition the code actually checks); re-run. This is the common case when the code is correct but the spec is loose.
   - **Code does NOT enforce the invariant.** This is a bug — feed it as a target to `colosseum-code-adversarial` or to the standard fix loop.
   - **Code enforces via a downstream layer the Quint model does not see.** Document the cross-layer dependence in the integration ledger.

### Deliverable

Write to `<project>/.colosseum/attacks/quint-adversarial-<ISO-date>.md`:

```markdown
# Quint-adversarial trace generation: <project>  —  <ISO-date>

- Quint spec: <path>
- Spec version: <git rev or frontmatter version>
- Invariants targeted: <N>
- Counterexamples found: <K>

## Per-invariant table

| Invariant | Bound | Result | Trace summary | Code enforcement | Verdict |
|---|---|---|---|---|---|
| `inv_b1_tally_write_once` | 10 | counterexample | `[CreateElection, SubmitBallot, CreateElection]` violates at step 3 | `CreateElection` handler at `crates/contract/src/handle.rs:118` does NOT check current phase | bug |
| `inv_s4_voter_partition` | 10 | held under bound | — | n/a | survived |

## Findings

| ID | Severity | Invariant | Trace | Fix recommendation |
|---|---|---|---|---|
| QA-01 | Major | `inv_b1_tally_write_once` | `[CreateElection, SubmitBallot, CreateElection]` | reject second `CreateElection` while any election is active |
```

### Worked example: verified-rcv CreateElection bug

Verified-rcv's intent stated `B1` (tally write-once per election) and the Quint model encoded `inv_b1_tally_write_once`. The contract code's `CreateElection` handler at `crates/contract/src/handle.rs` did NOT check the current phase — a second `CreateElection` would clobber the in-flight election's state including its tally. An intent-adversarial pass did NOT surface this bug; the intent stated B1 correctly, and adversarial critiques focused on intent-level concerns. A Quint-adversarial pass on `specs/rcv.qnt` running `quint run --invariant inv_b1_tally_write_once` produces the trace `[CreateElection { id: 0 }, SubmitBallot { id: 0, ... }, CreateElection { id: 0 }]` violating the invariant at step 3. Cross-reference to code at `handle.rs` identifies the missing phase check.

The intent-adversarial skill caught nothing of this kind before audit. The audit surfaced it as a Major finding. A Quint-adversarial pass at the spec's landing would have surfaced it mechanically.

### Distinction from `colosseum-lifecycle-adversary`

- **`colosseum-lifecycle-adversary`** is triggered by *new admin transitions* (Propose/Finalize/Cancel, timelocks, state archival). It extends the Quint model FIRST, then runs the trace generation. Use it when the spec is being extended.
- **This step** runs trace generation against an EXISTING Quint model with EXISTING invariants. Use it as a regular maintenance pass and at milestones.

Both produce trace deliverables in the same format. Use whichever skill matches your trigger; do not run both.

## Step 6: Persist verbatim

Create the directory `<project>/.colosseum/attacks/<spec-basename>-<ISO-timestamp>/` if multi-model, or use the flat `.colosseum/attacks/<spec-basename>-<ISO-timestamp>.md` file if single-model.

Multi-model layout:

```
.colosseum/attacks/<spec-basename>-<ISO-timestamp>/
├── meta.md                  # header with paths, round number, models dispatched
│                            # — REQUIRED: full per-voice model id (e.g.
│                            # `gateway/kimi-k2-6` not just "kimi"), endpoint
│                            # family (Anthropic / Google / OpenAI / Moonshot /
│                            # Zhipu / Mistral / Qwen / Goedel / etc.), and
│                            # finish_reason ({stop, length, error}). Gateway
│                            # ids drift between sessions, so the exact pin is
│                            # what makes the run reproducible.
├── claude.md                # Claude's verbatim attack report
├── local-<model-id>.md      # one per local model (e.g. `local-mistral-small-4-119b-2603.md`)
├── gateway-<model-id>.md    # one per gateway model (e.g. `gateway-kimi-k2-6.md`)
├── openai.md                # GPT's verbatim attack report (via OpenAI BYOK)
├── google.md                # Gemini's verbatim attack report (via Google BYOK)
└── synthesis.md             # YOUR overlap/divergence summary (clearly marked
                             # as orchestrator output, NOT a model output)
```

Single-model layout (unchanged from prior version):

```
.colosseum/attacks/<spec-basename>-<ISO-timestamp>.md
```

Each per-model file starts with a small metadata header:

```markdown
# Adversarial review: <spec-basename>  —  <provider> (<model id>)

- Spec under review: <absolute path>
- Intent document: <absolute path>
- Reviewed at: <ISO timestamp>
- Round: <N>
- Model id: <exact id, e.g. `kimi-k2-6`, `qwen3.6-27b-mlx`>
- Provider family: <Anthropic / Google / OpenAI / Mistral / Alibaba / Moonshot / Zhipu / OSS-GPT / etc.>
- Inference seat: <agent-subagent / lm-studio-local / gateway-<route> / openai-byok / google-byok>
- Elapsed (s): <float>
- Finish reason: <stop | length | error | tool_use>
- max_tokens: <integer>

---

<adversary's verbatim report>
```

Round number is determined by counting prior attack reports against the same spec basename in `.colosseum/attacks/`.

**Voice metadata discipline** (verified-rcv evidence): provider family + inference seat + finish_reason are load-bearing for synthesis. Family diversity is the actual signal multi-model dispatch produces; the synthesis must be able to distinguish "5 of 7 voices flagging the same bug" from "5 of 7 voices from the same provider family". Finish reason distinguishes "voice said its piece" (`stop`) from "voice ran out of budget mid-attack" (`length`) from "voice errored or timed out" (`error`) — the synthesis-time interpretation of the verdict depends on which.

When using the manifest tool (`colosseum_run.py`), these fields live in `run.json` under each voice's `metadata` object; the markdown header is a courtesy copy for human reviewers.

**Never edit any per-model report.** The whole point of multi-model adversarial is that each model's blind spots are different. Editing flattens them.

## Step 7: Synthesize overlap and divergence

Only after persisting verbatim reports, produce a synthesis. Mark it explicitly as orchestrator output. It is a *summary*, not a meta-attack — you do not get to add or weaken findings.

The synthesis is structured around **three required sections** (in addition to the standard verdict summary + voice roster):

### Section A: Overlap matrix — findings ordered by multi-voice support

Cluster the per-voice findings into *themes*. A theme is a single underlying issue. For each theme:

- A per-voice support table: which voice flagged the issue, at what severity, with which spec citation.
- A one-line consensus framing.
- A concrete fix recommendation.
- A multi-voice support count in the theme header (e.g., "5/7 voices").

Themes are listed in descending order of multi-voice support. Themes with only one voice flagging are explicitly tagged "single-voice but deep" (the voice's analysis is grounded and the finding is substantive — frequent for file-access voices like Claude-via-Agent that see things text-only voices miss) or "single-voice but suspect" (the synthesis voice's judgment that this is probably noise). Be explicit; do not paper over the difference.

### Section B: False positives identified

Voices fail in known ways. Synthesis must surface and refute the failure cases the multi-voice ensemble exposes:

- **Cross-block / cross-section confusion** — a voice flags a contradiction between two distinct sections / blocks but actually conflated them (e.g., a verified-rcv gpt-oss-120b "Block 6 self-contradicts" finding that actually conflated Block 5's idempotent self-loop with Block 6's transitional rejection).
- **Mis-read existing fix** — a voice flags a defect that the spec already addresses; re-reading the relevant section confirms the spec is correct.
- **Hallucinated content** — a voice cites text that doesn't appear in the spec, or attributes a property to a section that doesn't have it.
- **Misunderstanding of methodology terms** — a voice flags a "temporal_state_mismatch" but the property is genuinely temporal and correctly tagged.

Each false positive entry: which voice, which finding, the refutation (with cite — usually pointing at the spec text the voice missed or at another voice's correct reading). Synthesis is explicit because downstream readers (intent author, future agents) need to know which findings to NOT act on.

### Section C: Methodology disagreement worth surfacing (not a revision target)

When one voice **affirms** a property other voices **substantively critique**, this is a depth-of-attack divergence — not a real disagreement that requires action. Common shape: voice X notes "B6 is correctly tagged temporal" with shallow analysis; voices Y, Z, W critique B6's formulation with substantive arguments (e.g., the existential doesn't bind to the firing transition).

The synthesis surfaces the divergence so reviewers know the affirmation is shallow, not authoritative. It is not a revision target — the multi-voice critique stands; the single affirmation just records the depth-of-attack difference.

### Failure-mode catalog the synthesis must process

Verified-rcv calibration catalogues voice-level failure modes that synthesis must recognize:

- **Truncation** (`finish_reason: length`): voice ran out of output budget mid-attack-list. Content is partial; remaining findings unknown. Synthesis records but does not over-interpret a truncated voice's silence on a theme.
- **Reasoning-budget burnout**: reasoning model exhausted its hidden reasoning tokens before producing substantive visible output, or burned through visible output by repeating already-stated material (gemma-4-26b-a4b "Final check" loop after ~220 lines, observed in verified-rcv).
- **Degeneration**: voice produced syntactically valid but semantically empty content — tautology loops, abstract variable enumerations, prompt-template echoes (goedel-prover-v2-32b case + glm-4-7-flash's verdict-template echo, observed in verified-rcv).
- **Verdict-template echo**: voice's verdict line literally repeats the prompt's enumeration menu ("VERDICT: BREAKS | SURVIVES | INDETERMINATE") instead of choosing one. Verdict-extraction regex must filter; synthesis examines content for the implicit verdict.

Synthesis writer should test each voice's report for these failure modes before clustering its findings.

### Standard sections (in addition to A/B/C above)

- **Voice roster + verdict table** — at the top, one row per voice with: model id, family, channel, elapsed, finish_reason, verdict, byte count of visible content.
- **Verdict tally** — bucketed counts (BREAKS / SURVIVES / INDETERMINATE / ERROR).
- **Per-voice reports (verbatim)** — concatenation appendix; the `colosseum_run.py synthesize` tool produces this deterministically.

### Revision punch list (recommended)

For runs that return BREAKS / BREAKS-AGAIN, end the synthesis with an ordered punch list of revisions:

- Each entry: priority tier (CRITICAL | SERIOUS | EDITORIAL), voices supporting (count + names), concrete edit recommendation, citation to relevant spec lines.
- Ordered by multi-voice support × severity. Multi-voice criticals at the top; single-voice editorial items at the bottom.
- This is the artifact the next revision pass works against.

Write the synthesis to `synthesis.md` in the multi-model directory.

**Exemplar**: the verified-rcv `intent-revised` attack directory contains a reference implementation of this format (~300 lines, 7 voices, 16 themes catalogued, 5 false positives refuted, 1 depth-of-attack divergence surfaced, 17-item punch list).

## Step 8: Summarize for the user

After persisting, report:

- One-line per-voice verdict summary using explicit voice IDs (NOT bucket names): `claude-agent: BREAKS (3 critical, 5 serious) | openai/gpt-5.1-thinking: BREAKS (2 critical) | burnt/cloudflare-100/@cf/moonshotai/kimi-k2.6: SURVIVES | ds4/deepseek-v4-flash: BREAKS (1 critical) | google/gemini-3-pro: BREAKS (2 critical)`
- **Shared-finding count** — bugs surfaced by ≥2 models (high signal)
- **Unique-finding count** per model — blind-spot escapes
- The absolute path to the saved report directory (or single file)
- A suggested next step:
  - Shared critical findings → revise spec immediately, re-run this skill
  - Unique critical from one model → re-attack with that finding inlined as context in next round; if a second model also surfaces it, treat as confirmed
  - All `SURVIVES` across ≥3 family-diverse models → mature enough for downstream verification work
  - Mixed `INDETERMINATE` → providers had insufficient artifacts; surface the missing context and re-run

## Multi-round usage

When a spec has been revised after a prior round, invoke this skill again. By default, no adversary sees prior reports — fresh attention each round. The invoking user may optionally include the prior synthesis as additional context if they want adversaries to verify that specific prior attacks have been resolved.

When iterating, prefer the same `models` list across rounds — comparing round-N synthesis to round-N+1 synthesis is most informative when the panel composition is stable.

## What you do not do

- You do not edit any per-model attack report
- You do not advocate for the spec
- You do not skip the persistence step — every model's report becomes part of the project's verification history
- You do not invoke any adversary without both spec and intent in hand
- You do not silently fall back to single-model when a requested provider is unreachable. Report which providers were reached vs. failed; the user decides whether to proceed or retry.
- You do not run multiple full rounds in a single skill invocation; one round per call. The synthesis is per-round.

## Failure modes

- **Requested provider unavailable.** Surface the per-provider error. If at least one model returned a usable report, persist it and note the unavailability in the synthesis. If none returned usable reports, do not pretend a review happened — surface the failure and stop.
- **One model returns empty or malformed output.** Persist it verbatim anyway (the failure is itself data about that model's state). Note it in the synthesis. Do not retry silently — the orchestrator should not paper over adversary state.
- **Spec and intent are out of scope alignment.** Stop before invoking. Ask the user to confirm or revise alignment.
- **Multi-model requested but only one provider configured.** Tell the user which providers are missing and offer to proceed with what's available, or stop and configure.

## Spirit

Single-model adversarial is good. Multi-model adversarial is the methodology working at its intended strength. The cost of running every spec under multi-model is real (latency, dollars on cloud calls), so default to single-model for routine work and elevate to multi-model for spec milestones. Make the elevation easy and the persistence honest — every model's voice, in full, attached to the project's history. The synthesis is your job; the attacks are not.
