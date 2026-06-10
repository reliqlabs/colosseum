# Per-section adversarial dispatch — design

**Status**: design draft. Validates the per-section dispatch + file-access subagent dispatch improvements proposed in [methodology-improvements.md](../methodology-improvements.md).

**Problem this solves**:

1. **Gateway wall-time cap**: any single OpenAI-format request takes ≤240s upstream. `kimi-k2-6` hits the cap at `max_tokens ≥ 16K`; the timeout floor is wall-time, not token-count. *Per-section dispatch* keeps each single request to ~30-60s by emitting 1-3K output tokens at a time across N section-scoped calls.
2. **Inlined-everything context size**: each voice currently ingests the entire ~25-30K-token intent.md per call. For single-component dogfood it is wasteful but tractable; for multi-component projects it would exceed reliable-attention budgets across all but frontier-tier voices.

The two failure modes are addressed by two related but distinct patterns:

- **Static per-section slicing** (inline dispatch): orchestrator slices `intent.md` by section header at dispatch time; each call gets only its section + a small cross-section context appendix. No file-access primitive needed at the voice side.
- **Dynamic file-access subagent** (subagent dispatch): voice receives a file handle + brief; the voice's agent loop decides which sections to read. OpenCode-native.

Inline dispatch is the cheap immediate win. Subagent dispatch is the architecturally clean shape for system-of-intents work. Validate inline dispatch first; graduate to subagent dispatch when system-of-intents work begins.

---

## Inline dispatch — Static per-section slicing (no OpenCode dependency)

Orchestrator slices `intent.md` at top-level `##` headers (with a manual override for `## 2. Behaviors` → split at `### 2.5 Structured behavior blocks` because §2.5 is the type-definition section that's its own attack target).

### Slice plan for verified-rcv intent

| Slice | Sections | Approx tokens | Attack emphasis |
|---|---|---|---|
| `scope` | §1, §5, §6.4–6.6 | ~1.5K | Who can do what; out-of-scope claims that should be in-scope |
| `behaviors-core` | §2.1–2.4 | ~3K | Input/output worked examples; arithmetic; edge case completeness |
| `behaviors-types` | §2.5 | ~5K | Type signatures: `Tally_spec`, `IRV_spec`, `EnclaveImage`, `image_registration_honest`, `canonical_serialization`, transaction trace model |
| `state-invariants` | §3.1 | ~1K | S1–S5+ formulations; set-once write-discipline correctness |
| `temporal-invariants` | §3.2 | ~2K | B1–B10 + `B10_lean`; cross-layer tagging; ∀-per-key formulation |
| `failure-modes` | §4 | ~2.5K | Each of §4.1–§4.9; severity tagging; in/out-of-scope correctness |
| `trust-quartz` | §6.1–6.3 | ~2.5K | Quartz inheritance table; de-retraction status block; `commitHashE` row |
| `scenarios` | §8.1–8.6 | ~3K | Witness-correctness for each invariant; trace coverage |
| `off-chain-witness` | §8.7 | ~1.5K | B10 cross-layer 6-step discharge; `B10 ← B10_lean ∧ image-identity-binding ∧ B8` factorization |

Total: ~22K tokens of intent, sliced into ~1.5–5K-token attack units. Each voice does 9 calls; total per-voice input is ~22K tokens still, but spread across 9 calls each well under any timeout.

### Context appendix (per-call, shared across all slices for a voice)

Each call receives a small fixed appendix to keep cross-section reasoning grounded:

```
=== CONTEXT (read-only, do not attack — for grounding only) ===

System under review: verified-rcv, an IRV CosmWasm smart contract with
TDX-enclave tabulation via Quartz/dstack/zkdcap.

Invariant labels (full bodies in §3.1 / §3.2 — not inlined here):
  state:     S1 candidate-set-immutable, S2 deadline-immutable,
             S3 tally-set-once, S4 sender-bound, S5 set-once-write-discipline
  temporal:  B1..B5, B6 (∀-per-key per submitter), B7..B9
  cross-layer: B10 (= B10_lean ∧ image-identity-binding ∧ B8)
  lean-internal: B10_lean

Type signatures (full definitions in §2.5):
  Tally_spec : EncryptedBallots × Schedule × ResolverPolicy → TallyResult
  IRV_spec   : RankedBallots × CandidateSet → IRVResult
  EnclaveImage : Bytes → Bytes  (image_extract)
  canonical_serialization = Borsh

=== END CONTEXT ===

=== TARGET SECTION (under attack) ===
<the slice body>
=== END TARGET SECTION ===
```

### Per-call brief

Reusable across all 9 slices, parameterized by `<slice-name>`:

```
You are attacking ONLY the section labelled "TARGET SECTION" above.

The context block is for grounding — do not attack content that is only
present in the appendix (those sections will be attacked in their own calls).
Cite ONLY text from the target section.

If you spot a problem whose root cause is in another section (e.g. a missing
type definition or a misclassified invariant), record it under "Cross-section
suspicion" with a pointer; another call will examine that section.

Output structure:

# <voice> — slice <slice-name>

## Attacks on this slice
### <title> [critical|serious|cosmetic]
- Category: <attack category>
- What's wrong: ...
- Cite: > <quoted target-section text>
- Fix recommendation: ...

## Cross-section suspicion
- <pointer-only items, no cites required>

## VERDICT (slice-local): BREAKS-AT-SLICE | SURVIVES-SLICE | INDETERMINATE
```

A voice's overall verdict is `SURVIVES` only when all 9 slice-local verdicts are `SURVIVES-SLICE`.

### Output file shape

Each voice produces ONE per-voice file (same shape as today's dispatch) by concatenating its 9 slice outputs with section headers. The orchestrator does the concatenation; the voice produces 9 independent outputs.

```
.colosseum/attacks/<run-tag>/
├── run.json
├── per-section/                      # NEW: intermediate per-slice files
│   ├── kimi-k2-6/
│   │   ├── scope.md
│   │   ├── behaviors-core.md
│   │   └── ...
│   ├── glm-4-7-flash/
│   │   └── ...
│   └── ...
├── gateway-kimi-k2-6.md              # aggregated (same shape as today)
├── gateway-glm-4-7-flash.md
├── ...
└── synthesis.md
```

### Orchestrator implementation sketch

Subclass / fork `verified-rcv/.colosseum/scripts/fan_out_dispatch.py`:

1. Add `slice_intent_md(path) → {slice_name: slice_body}` parser (regex on `## N. ` and `### N.M ` headers, group by manual plan above).
2. Replace `build_user_prompt(full_intent)` with `build_per_section_prompts(slice_dict) → {slice_name: prompt_text}` that injects the shared context appendix + the slice body.
3. Dispatch loop becomes `for voice in voices: for slice_name, prompt in prompts.items(): call_endpoint(...)` with per-voice intermediate-file writes.
4. Final aggregation step: for each voice, concatenate its per-slice files with section headers into the canonical per-voice file.
5. Manifest schema (`run.json`) gains `voice.metadata.per_section: true` and `voice.metadata.slices_completed: [list]`.

Wall-time budget per voice (sequential slice calls):
- Local LM Studio voices: 9 × 30s = ~5 min/voice (down from current ~30 min for reasoning voices)
- Gateway voices: 9 × 40s = ~6 min/voice (down from current 4 min for non-truncated voices but no truncation risk)
- Total fan-out at ~30s/call sequential: 9 voices × 9 slices × 30s = ~40 min worst case; sequential per-voice but voices-in-parallel: ~6 min worst case

### Risk catalog (inline dispatch)

- **Cross-section findings missed**: an attack that requires reading two non-adjacent sections won't get caught by either single-slice call. *Mitigation*: the "Cross-section suspicion" channel; synthesis voice surfaces multi-slice resonance.
- **Slice arithmetic over-coupling**: §2.5 defines types used in §3 invariants; the §3 slice has only label-level appendix for these. *Mitigation*: appendix carries type signatures, not just labels, for the load-bearing definitions.
- **Section boundaries don't match attack-target granularity**: e.g., B10 has formulation in §3.2, discharge in §8.7. Multi-call coordination needed. *Mitigation*: explicit listing of "this slice's target invariants" at top of brief.
- **Synthesis cost goes up**: 9 partial files per voice × 6+ voices = 54+ files for synthesis. *Mitigation*: orchestrator aggregates per-voice first so synthesis sees the same shape as today.
- **Voice quality at smaller per-call context**: some models perform worse at small inputs (under-stimulated). Calibrate per-voice. Not believed to be a major issue.

---

## Subagent dispatch — OpenCode file-access agent loop

Inline dispatch is enough to validate the timeout fix. Subagent dispatch graduates to OpenCode's native subagent shape, where the voice's agent loop decides which sections to read rather than the orchestrator deciding for it.

### Why graduate

Inline dispatch's static slicing is correct for verified-rcv (intent layout known, sections well-bounded, attack targets enumerable). For system-of-intents projects with N components × ~10 sections each, static slicing produces a quadratic explosion of calls. Dynamic file-access lets each voice's attack hypothesis drive its own read pattern — typically O(few) reads per attack hypothesis, regardless of system size.

### OpenCode agent definition

File: `verified-rcv/.opencode/agent/spec-adversary.md` (or `colosseum/agents/opencode/spec-adversary.md` for repo-wide reuse).

```yaml
---
description: Adversarial spec reviewer for Colosseum methodology.
  Reads target spec sections on demand, surfaces grounded attacks.
mode: subagent
model: <chosen-by-orchestrator>
permission:
  read: allow
  write:
    - "**/.colosseum/attacks/**/per-section/**"
  bash: deny
  webfetch: deny
tools:
  read: true
  write: true
  grep: true
  glob: true
  edit: false
  bash: false
---

{{system-prompt-from-colosseum-spec-adversary.md}}

You attack ONE section of the target spec per invocation. You may read
other sections to ground or refute your finding, but your output attacks
only the named target.

INPUTS: provided at invocation time:
  - TARGET_SPEC: absolute path to the intent doc
  - TARGET_SLICE: section identifier (e.g. "temporal-invariants" or "§3.2")
  - OUTPUT_PATH: absolute path to write your slice-local report

PROCEDURE:
  1. Read TARGET_SPEC at TARGET_SLICE.
  2. Optionally read other sections for grounding (declare what you read
     and why in your output).
  3. Write your slice-local report to OUTPUT_PATH using the structure
     from {{per-slice-output-template}}.
```

### Orchestrator-side (still Python)

```python
# pseudocode
for voice in voices:
    for slice_name in slices:
        subprocess.run([
            "opencode", "run",
            "--agent", "spec-adversary",
            "--model", voice.model_id,
            "--",
            f"TARGET_SPEC={intent_path}",
            f"TARGET_SLICE={slice_name}",
            f"OUTPUT_PATH={out_dir}/per-section/{voice.id}/{slice_name}.md",
        ], check=True, timeout=300)
```

(OpenCode `run` is non-interactive; the agent reads/writes via its tool permissions.)

### What OpenCode buys us over inline dispatch

- **Subagent-decided reads**: the voice's ReAct loop reads what it needs; no orchestrator slicing decisions baked into Python.
- **Single agent definition reused across voices**: model selection is per-invocation, not per-script.
- **Tool permission scopes are auditable**: `permission.read: allow` is more declarative than orchestrator-side context injection.
- **Direct hand-off to system-of-intents work**: when the target becomes "this component intent + linked boundary docs", the agent's read tool handles cross-doc reads natively.

### What it costs

- **OpenCode auth setup**: ~~per-model credentials in OpenCode's config (separate from the colosseum `.env`). Friction for first-time setup.~~ **Already done.** `~/.config/opencode/opencode.jsonc` at v1.14.50 already configures both the LM Studio provider and the Burnt AI Gateway provider with the same model roster (kimi-k2-6, glm-4-7-flash, gpt-oss-120b, plus claude-opus-4-6/4-7, claude-sonnet-4-6, gemini-2-5-flash, gemini-3-1-flash-lite). Verified 2026-05-16.
- **Less direct control of HTTP retries / per-route timeouts**: OpenCode wraps the HTTP call; the gateway-bug-aware retry-on-408 path we currently have in `fan_out_dispatch.py` would need to be re-implemented at OpenCode's layer (or accepted as best-effort).
- **Opaque agent traces**: from the orchestrator's perspective, OpenCode's per-subagent reasoning is just stdout + exit code. Per-section-read telemetry would have to be in OpenCode's own logs.

### Discovery: gateway URL differs between OpenCode and our `.env`

The Burnt gateway has at least two routes configured:
- `/u/c5nksc/colosseum/v1` (colosseum `.env`; used by `external-model-mcp` + `fan_out_dispatch.py`)
- `/u/c5nksc/openai/v1` (OpenCode `opencode.jsonc`)

Different API keys for each. Worth probing whether the `/openai/v1` route has the same Cloudflare 240s wall-time cap (Bug 3) and the same Anthropic Cloudflare 524 ceiling (Bug 4). If the routes are independent proxies, we may already have a workable Anthropic-via-gateway path through OpenCode that we don't have through the colosseum MCP. Adversarial result either way is informative for the methodology.

### Discovery: LM Studio model list drift

OpenCode `opencode.jsonc` references `qwen/qwen3.6-27b`, `qwen/qwen3-coder-next`, `nvidia/nemotron-3-nano`, `google/gemma-4-26b-a4b`, `leanstral-2603`. Local `lms ls` shows `qwen3.6-27b-mlx` (different id), `mistral-small-4-119b-2603` (not in OpenCode config), `goedel-prover-v2-32b` (excluded from adversarial spec review per theorem-prover specialist exclusion). Reconcile before dispatch — either pin OpenCode to the actual loaded ids, or accept that some voices are gateway-only via OpenCode and run local voices through the existing Python dispatch.

### Risk catalog (subagent dispatch)

- **OpenCode version drift**: agent-definition schema is evolving. Pin OpenCode version in the colosseum INSTALL.md when this lands.
- **Subagent over-reading**: a paranoid agent might read every section every time, eliminating the timeout benefit. *Mitigation*: brief instructs "read narrowly; declare cross-section reads with reason." Validate empirically.
- **Model-side compatibility**: not every model OpenCode supports has parity with its OpenAI-format equivalent. Some gateway voices may behave differently under OpenCode's prompt scaffolding.

---

## Decision: with OpenCode already configured, subagent dispatch becomes the natural choice

The original sequence (inline dispatch first, subagent dispatch later) was justified by subagent dispatch's setup-cost — separate provider config in OpenCode, model registration, key management. After verifying `~/.config/opencode/opencode.jsonc`, that cost is already paid. The recommendation revises:

1. **Now (while 3rd-pass synthesis is being assembled)**: implement subagent dispatch as `verified-rcv/.opencode/agent/spec-adversary.md` + a thin Python wrapper that iterates `(voice, slice)` pairs and invokes `opencode run` per pair. Use the slice plan from inline dispatch above (it's harness-agnostic).

2. **Before the 4th attack runs**: reconcile the LM Studio model-list drift in `~/.config/opencode/opencode.jsonc` (or scope the OpenCode dispatch to gateway voices only, with local voices via the existing Python dispatch).

3. **Concurrent benefit experiment**: probe whether the OpenCode `/u/c5nksc/openai/v1` gateway route has different timeout behavior than the colosseum `/u/c5nksc/colosseum/v1` route. If it does, methodology gains a workable Anthropic-via-gateway path; if it doesn't, the per-section pattern still wins via per-call wall-time bound.

4. **inline dispatch remains worth keeping as a fallback**: if OpenCode dispatch surfaces an unforeseen problem (model ID mismatch, ReAct loop diverging, MCP plumbing issue), the pure-Python inline dispatch is the no-OpenCode escape hatch. Implementation is small enough (~50 lines on top of current `fan_out_dispatch.py`) that the option-value justifies keeping it on the candidate list, but it doesn't have to ship if subagent dispatch works.

5. **Eventual back-port to methodology**: subagent dispatch alone validates the per-section dispatch + file-access subagent dispatch improvements simultaneously (static slicing + dynamic file-access). The colosseum-adversarial SKILL Step 4 gets a "Dispatch modes" subsection naming two modes — inlined (current default) and OpenCode subagent (recommended for ≥25K-token intents).

## Open questions to resolve at implementation time

- Does the local LM Studio dispatch benefit from per-section too? (Wall-time-wise: not strictly needed — local has no 240s cap. Quality-wise: smaller context may help reasoning models like qwen3.6 stay on task.)
- What's the right verdict-aggregation rule when slice-local verdicts disagree across slices? Proposed: voice verdict = max severity of any slice's findings; SURVIVES requires all slices SURVIVES-SLICE.
- Does the context appendix introduce its own attack target (false grounding)? Proposed: clearly tag the appendix as "context-only, not attacked here"; the synthesis voice catches appendix-induced confusion as a methodology-level finding.
- Should the orchestrator's slicing plan be in code (Python dict) or in a sidecar config file (YAML)? Proposed: sidecar `slice-plan.json` so the slicing is auditable and editable without code changes.
