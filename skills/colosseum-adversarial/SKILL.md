---
name: colosseum-adversarial
description: Run the Colosseum spec adversary against a specification — single-model or multi-model. Reads the spec and the intent document, dispatches the colosseum-spec-adversary subagent (Claude) and optionally fans the same attack out to local (lm-studio-mcp) and/or cloud (external-model-mcp) providers, captures each structured report verbatim, persists them under .colosseum/attacks/, and summarizes overlap and divergence. Use when a draft spec needs scrutiny before commitment, or to re-attack a revised spec after a prior round's findings were addressed.
---

You are orchestrating an adversarial review of a specification. The methodology rests on the claim that *the unit of trust is surviving adversarial scrutiny*, not consensus. Your job is the orchestration: locate the artifacts, dispatch one or more adversaries, capture their output verbatim, persist it, and report overlap + divergence.

You are not the adversary. You do not produce the attacks. You do not soften them. You provide each adversary with everything it needs and stand out of its way.

## Single-model vs multi-model

This skill supports two modes:

- **Single-model (default)** — invoke the `colosseum-spec-adversary` subagent (Claude). Fast, free under the Claude Code subscription, no setup.
- **Multi-model** — invoke Claude *and* fan the same attack prompt out to local models (`lm-studio-mcp`) and/or cloud providers (`external-model-mcp`). Genuine family diversity, much closer to the methodology's "adversarial beats consensus" claim. Slower; cloud calls cost money.

The user selects via the `models` parameter. Default is `["claude"]`. Recommended for routine spec milestones: `["claude", "local"]` (Claude + local floor; free). Recommended for high-stakes spec milestones: `["claude", "local", "openai", "google"]`.

## Step 1: Locate the artifacts

Ask the user for, or determine from context:

- **Path to the spec under review** — the artifact being attacked. May be a Lean file, Quint module, Verus annotations in a Rust source, a `#[kani::proof]` harness, or any other spec artifact.
- **Path to the intent document** — the human-anchored source of truth the spec is supposed to encode. Typically `intent.md` at the project root, but allow override.
- **Optional context** — paths to existing tests, related specs, prior attack reports, type signatures, anything that strengthens grounding.
- **Project root** — where `.colosseum/attacks/` should be created. Infer from the spec's location if not given.
- **Models to dispatch** — list. Subset of `["claude", "local", "openai", "google"]`. Default `["claude"]`. Ask the user if not specified for a non-trivial spec — the multi-model option is a load-bearing capability and should not be silently bypassed.

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

## Step 4: Dispatch the adversaries

Dispatch happens in parallel — every requested provider attacks concurrently.

**Two dispatch shapes are supported**:

- **In-process** (this section) — the running Claude Code session dispatches each voice as a child Agent / MCP call, blocks until all return, then synthesizes. Works when every voice can be invoked from one harness.

- **Harness-agnostic manifest** (`scripts/colosseum_run.py` — v0.3+) — for cases where voices live in different harnesses (e.g., Claude voice runs in Claude Code with the Agent subagent, non-Claude voices run in OpenCode with native multi-provider subagents + file access + step budgets that work around per-voice timeouts). Each harness reads + updates a shared `run.json` manifest; the manifest is the state machine. See `colosseum/scripts/README.md` for the schema, lifecycle, and CLI usage. Recommend this shape when (a) the Anthropic-via-gateway route is unviable for the non-Claude voices (Bug 4) and Claude must run in-process, or (b) voices need file-access tools that the MCP-call channels can't provide.

- **claude** — invoke the `colosseum-spec-adversary` subagent via the Agent tool. Claude operates with full tool access (Read, Grep, Glob, Bash); the inlined prompt body is supplemental, not the only input. This subagent can re-read files, check related code, run diagnostics.

- **local** — call `lm-studio-mcp`'s `fan_out_local` with `models=` set to the user's preferred local pair (default: all loaded). The inlined prompt is the only input — local models have no file access. Quality is lower than Claude / cloud frontier but lineage is genuinely different.

- **openai** — call `external-model-mcp`'s `query_openai(prompt=...)`. The inlined prompt is the only input.

- **google** — call `external-model-mcp`'s `query_google(prompt=...)`. The inlined prompt is the only input.

- **gateway** — call `external-model-mcp`'s `query_gateway(prompt=..., model="<gateway-model-id>")`. The gateway is an operator-curated OpenAI-format multi-model endpoint; available `model` ids drift with operator curation (current set: `claude-opus-4-7`, `claude-sonnet-4-6`, `gemini-2-5-flash`, `gemini-3-1-flash-lite`, `glm-4-7-flash`, `gpt-oss-120b`, `kimi-k2-6`). Picking the gateway gives the cleanest path to family-diverse non-Western reasoning voices (Moonshot `kimi-k2-6`, Zhipu `glm-4-7-flash`) without provisioning per-provider BYOK keys.

  Configuration: the MCP loads `COLOSSEUM_GATEWAY_BASE_URL` + `COLOSSEUM_GATEWAY_API_KEY` + `COLOSSEUM_GATEWAY_DEFAULT_MODEL` from `.env` (gitignored). Search order: `$COLOSSEUM_DOTENV` env override → `CWD/.env` → `<colosseum-repo-root>/.env` → `~/.colosseum.env`. Each project's working directory is the natural place to drop a project-local `.env` so the MCP picks it up when launched with that CWD. After editing `.env` the MCP process must restart (env vars are read at MCP start, not per-call) — easiest is to restart the Claude Code session.

  **Timeout caveats** (observed 2026-05-14; see `<project>/.colosseum/gateway-bugs-2026-05-14.md` Bugs 3+4): there are *two* timeout layers in front of the gateway:
  
  - **Gateway-wide ~240s ceiling** (Bug 3, likely Cloudflare inbound proxy). Affects every route. Calibrate `max_tokens` per upstream model's generation speed to fit under it. Empirical 2026-05-14 values at a ~22K-token prompt:
    - `kimi-k2-6`: ≤ 8192 (133s); 16K blows cap (238s, HTTP 408)
    - `glm-4-7-flash`: ≤ 16384 (152s); 24K blows cap (238s, HTTP 408)
    - `gpt-oss-120b`: 16K finished in 47s, much higher should be safe
    - Prompt length is a free variable; pin observed elapsed + max_tokens in your meta.md
  - **Anthropic-route ~127s ceiling** (Bug 4, Cloudflare 524). Both `claude-opus-4-7` and `claude-sonnet-4-6` hit it on long+high-budget dispatches. Anthropic-via-gateway is currently unviable for long-output adversarial passes. **For the "Claude voice" slot in a multi-model ensemble, run Claude via the Agent subagent** (file-access, no gateway dependency) — that path was the dispatch-plan recommendation anyway.
  
  **Parameter quirk**: `claude-opus-4-7` rejects the `temperature` request parameter (HTTP 400 "`temperature` is deprecated for this model"). Omit `temperature` when calling that model id. The MCP's `query_gateway` accepts `temperature=None` to opt out.
  
  Pin the exact model id + max_tokens + observed elapsed in your dispatch ledger so the timeout shape is reproducible across runs.

  **Reproducibility discipline**: gateway model ids are operator-curated and change between sessions; record the exact `model` parameter you invoked in your meta.md so future re-runs are honest.

(For "openai" and "google" together, you may use `external-model-mcp`'s `fan_out_query(prompt, providers=["openai", "google"])` for one round-trip. The gateway is per-model — there is no fan-out across gateway models in one MCP call; dispatch them as separate `query_gateway` calls in parallel, or use a project-local Python wrapper that reads the same `.env` and posts to the gateway directly. Verified-rcv's `.colosseum/scripts/fan_out_dispatch.py` is one such pattern.)

### Excluded model classes — theorem-prover specialists

**Do not include theorem-prover specialist models (e.g., `goedel-prover-v2-32b`, ProofGPT-class, math-tactic-tuned models) in adversarial spec review.** These models pattern-match the prompt as a *proof goal* and attempt Lean / Coq tactics rather than treating the spec as a target to *attack*. Round 3a (verified-rcv) included goedel-prover-v2-32b in an 8-voice fan-out and observed 8K tokens of degenerate tautology loops with abstract variable lists — wall time 852 seconds, output unusable. Use these models at the **verify-pyramid layer** instead (proof completion / tactic suggestion via `mcp__goedel__propose_lean_tactic`).

### Cross-session local-model contention (LM Studio ops notes)

When multiple agents work on related projects in parallel, both may invoke `mcp__lm-studio__*` against the same local LM Studio instance. With LM Studio configured for JIT loading + auto-evict-on-different-model (the typical consumer-hardware default), requests from one session can evict the model another session is mid-response on. Symptom: `HTTP 400: {"error":"Model unloaded."}` errors mid-dispatch.

Three discipline items:

1. **Pre-load each model before dispatch** via `lms load <model> --gpu max` (synchronous). Forces the model fully into memory before the chat-completion request fires. The verified-rcv dispatch wrapper at `verified-rcv/.colosseum/scripts/fan_out_dispatch.py` does this via a `lms_load` helper.
2. **Retry-on-unload up to 2 times** in the dispatch wrapper. Catches the race between pre-load and chat-completion that the cross-session contention introduces.
3. **Coordinate cross-session dispatch** when two agents work in parallel: one fan-out at a time across sessions, or accept best-effort with retries. The `colosseum_run.py` manifest protocol gives a natural coordination point — both sessions read + update the same `run.json`.

Wait for all parallel dispatches to complete. Capture each response.

## Step 5: Persist verbatim

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

**Voice metadata discipline** (Round 3a evidence): provider family + inference seat + finish_reason are load-bearing for synthesis. Family diversity is the actual signal multi-model dispatch produces; the synthesis must be able to distinguish "5 of 7 voices flagging the same bug" from "5 of 7 voices from the same provider family". Finish reason distinguishes "voice said its piece" (`stop`) from "voice ran out of budget mid-attack" (`length`) from "voice errored or timed out" (`error`) — the synthesis-time interpretation of the verdict depends on which.

When using the manifest tool (`colosseum_run.py`), these fields live in `run.json` under each voice's `metadata` object; the markdown header is a courtesy copy for human reviewers.

**Never edit any per-model report.** The whole point of multi-model adversarial is that each model's blind spots are different. Editing flattens them.

## Step 6: Synthesize overlap and divergence

Only after persisting verbatim reports, produce a synthesis. Mark it explicitly as orchestrator output. It is a *summary*, not a meta-attack — you do not get to add or weaken findings.

The synthesis is structured around **three required sections** (in addition to the standard verdict summary + voice roster):

### Section A: Overlap matrix — findings ordered by multi-voice support

Cluster the per-voice findings into *themes*. A theme is a single underlying issue (e.g., "B9 vacuity due to retracted Quartz substrate"). For each theme:

- A per-voice support table: which voice flagged the issue, at what severity, with which spec citation.
- A one-line consensus framing.
- A concrete fix recommendation.
- A multi-voice support count in the theme header (e.g., "5/7 voices").

Themes are listed in descending order of multi-voice support. Themes with only one voice flagging are explicitly tagged "single-voice but deep" (the voice's analysis is grounded and the finding is substantive — frequent for file-access voices like Claude-via-Agent that see things text-only voices miss) or "single-voice but suspect" (the synthesis voice's judgment that this is probably noise). Be explicit; do not paper over the difference.

### Section B: False positives identified

Voices fail in known ways. Synthesis must surface and refute the failure cases the multi-voice ensemble exposes:

- **Cross-block / cross-section confusion** — a voice flags a contradiction between two distinct sections / blocks but actually conflated them (e.g., Round 3a's gpt-oss-120b "Block 6 self-contradicts" finding that actually conflated Block 5's idempotent self-loop with Block 6's transitional rejection).
- **Mis-read existing fix** — a voice flags a defect that the spec already addresses; re-reading the relevant section confirms the spec is correct.
- **Hallucinated content** — a voice cites text that doesn't appear in the spec, or attributes a property to a section that doesn't have it.
- **Misunderstanding of methodology terms** — a voice flags a "temporal_state_mismatch" but the property is genuinely temporal and correctly tagged.

Each false positive entry: which voice, which finding, the refutation (with cite — usually pointing at the spec text the voice missed or at another voice's correct reading). Synthesis is explicit because downstream readers (intent author, future agents) need to know which findings to NOT act on.

### Section C: Methodology disagreement worth surfacing (not a revision target)

When one voice **affirms** a property other voices **substantively critique**, this is a depth-of-attack divergence — not a real disagreement that requires action. Common shape: voice X notes "B6 is correctly tagged temporal" with shallow analysis; voices Y, Z, W critique B6's formulation with substantive arguments (e.g., the existential doesn't bind to the firing transition).

The synthesis surfaces the divergence so reviewers know the affirmation is shallow, not authoritative. It is not a revision target — the multi-voice critique stands; the single affirmation just records the depth-of-attack difference.

### Failure-mode catalog the synthesis must process

Round 3a's evidence base catalogues voice-level failure modes that synthesis must recognize:

- **Truncation** (`finish_reason: length`): voice ran out of output budget mid-attack-list. Content is partial; remaining findings unknown. Synthesis records but does not over-interpret a truncated voice's silence on a theme.
- **Reasoning-budget burnout**: reasoning model exhausted its hidden reasoning tokens before producing substantive visible output, or burned through visible output by repeating already-stated material (Round 3a's gemma-4-26b-a4b "Final check" loop after ~220 lines).
- **Degeneration**: voice produced syntactically valid but semantically empty content — tautology loops, abstract variable enumerations, prompt-template echoes (Round 3a's goedel-prover-v2-32b case + glm-4-7-flash's verdict-template echo).
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

**Exemplar**: `verified-rcv/.colosseum/attacks/intent-revised-2026-05-14T200029Z/synthesis.md` (Round 3a) is the reference implementation of this format. ~300 lines, 7 voices, 16 themes catalogued, 5 false positives refuted, 1 depth-of-attack divergence surfaced, 17-item punch list.

## Step 7: Summarize for the user

After persisting, report:

- One-line per-model verdict summary: `claude: BREAKS (3 critical, 5 serious) | openai: BREAKS (2 critical) | google: SURVIVES | local-qwen: BREAKS (1 critical)`
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
