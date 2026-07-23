# Panel-resolver live verification: 2026-07-24

Closes the `ctx.models.family` gap left open by
`calibration/2026-07-23-omp-panel-e2e/` (its "does NOT establish" list, item 4).

## Setup

- Temp project scaffolded with
  `scripts/colosseum_init.py --harness omp /tmp/panel-live`; the extension is
  installed project-local at `.omp/extensions/colosseum-panel-resolver.ts`.
- Driver: `omp -p --cwd <proj> --model anthropic/claude-haiku-4-5
  --auto-approve`, one Python eval cell per run.
- OMP 17.0.7. The resolver itself makes no model calls; it only queries the
  model registry, so this is cheap and deterministic apart from registry
  contents.

## What this establishes (live, not simulated)

- The project-local extension loads in a real OMP session and registers
  `colosseum_panel_resolve`. No OMP source change, no global config change.
- `ctx.models.list()` / `.resolve()` / `.family()` execute live and behave as
  the published `ExtensionModelQuery` types describe.
- **Positive.** `large-project` resolves both active seats
  (`openai-codex/gpt-5.6-sol`, `fireworks/glm-5.2`) and reports
  `family_distinctness_checked: true`, source
  `OMP ctx.models.family runtime comparison (resolver)`.
- **Negative (family).** A profile whose two seats carry *distinct*
  `declared_family` labels but both resolve to Anthropic is rejected:
  `two seats resolved to the same model family despite distinct
  declared_family labels`. The check discriminates; it is not hardcoded true on
  the success path. This is exactly the defense the stdlib `panel_roster`
  loader cannot provide.
- **Negative (availability).** A seat whose only candidate is unregistered is
  rejected: `no available model for seat b`.
- The SKILL's documented wiring runs end-to-end:
  `exec(read("skill://colosseum-panel/panel_roster.py"))` →
  `normalize_roster(tool.colosseum_panel_resolve(...))` → usable roster.
- Real `agent()` dispatch through resolver-composed, provider-qualified
  `provider/model:thinkingLevel` selectors, confirming OMP accepts that form:
  `anthropic/claude-haiku-4-5:low`, and **both active frontier seats at the
  `max` level the profile actually configures**:
  `openai-codex/gpt-5.6-sol:max` and `fireworks/glm-5.2:max` each returned
  `PONG`. This is authenticated inference, not registry listing.
- Thinking-level anomaly, recorded not diagnosed: under `agent()`,
  `openai-codex/gpt-5.6-sol` fails at `:low` and with no level suffix
  (`RuntimeError: agent() subagent 'task' failed`) while succeeding at `:max`;
  the same model works as a direct `omp -p --model` driver. Anyone lowering a
  seat's `thinking_level` off `max` must re-verify dispatch.

## Two defects this run found and fixed

1. **Dispatch identity was under-specified.** The resolver returned a bare
   `model.id`; `omp_panel.py` dispatches `resolved_model`, and its own comment
   already documented provider-qualified selectors. A bare id discards the
   provider that `ctx.models.resolve()` selected and family-checked, and can
   reroute a duplicate id to a different provider. The resolver now returns
   `${provider}/${id}`, keys its availability set the same way, and records the
   real `model.provider` in `resolved_provider`, previously *always* the empty
   string in live runs because `providerOf()` parsed a bare id that has no
   `/`. Live evidence records were therefore losing which provider served each
   seat. (No duplicate bare ids exist in this environment, so the misroute
   hazard was latent here, not active.)
   Regression: **R32** (`tests/r32_resolver_contract.py`) executes the real
   `omp-panel-resolver.ts` under Bun with a faked `ExtensionAPI` and
   `ctx.models` (no model calls), asserting the canonical selector, the real
   provider, and provider-qualified availability keying. Mutation-checked: it
   fails 5 assertions against the pre-fix resolver, where a model resolvable
   only under an absent provider (`pz/m3`) was wrongly accepted as bare `m3`.
2. **`normalize_roster` did not accept the real proxy shape.** The eval
   `tool.<name>` proxy returned `{"text": "<json>"}`; the normalizer handled
   the roster directly, `{"details": …}`, `{"content": [{"text": …}]}`, and raw
   JSON strings, but not that. Because the SKILL is fail-closed on roster
   resolution, this raised and would have blocked *every* panel run in this
   environment. Branch added; regression tests in R31 cover the shape and its
   fail-closed negative.

Both are the same recurring class as the earlier `make_evidence_gate` and
`normalize_roster` catches: documented wiring not matching the real runtime
contract. Only a live run surfaces them.

## Environment correction

`glm-5.2` **is** available here under provider `fireworks`
(`fireworks/glm-5.2`): registry-listed, resolvable by the resolver, and
confirmed to serve real inference at `fireworks/glm-5.2:max`. The earlier
"`glm-5.2` is not authed in this environment" note was wrong, and its evidence
was wrong too: it came from reading the trailing `yes`/`no` column of
`omp models` as availability when that column is `images`. Registry listing
alone would not have established an authenticated inference path either: the
resolver makes no model calls, so only the `agent()` dispatch above does.

## What this does NOT establish

- **Panel quality / calibration.** OMP routes remain `calibration: pending`.
  Nothing here shows a panel beats a single `@plan`/`@advisor` pass.
- **A full Sol+GLM two-family panel end-to-end.** Both seats are proven to
  *resolve* and to *dispatch* single `agent()` calls at `:max`, but the three
  barriered waves (drafts → blinded cross-review → synthesis), quorum, and
  evidence capture were not run on this roster.
- **`milestone-review`** against a real project's `itf_replay`-produced G1
  records. Still EXPERIMENTAL.

## Reproduce

```sh
uv run --script scripts/colosseum_init.py --harness omp /tmp/panel-live
cp templates/omp-panel-resolver.ts /tmp/panel-live/.omp/extensions/colosseum-panel-resolver.ts
omp -p --cwd /tmp/panel-live --model anthropic/claude-haiku-4-5 --auto-approve \
  "Run one Python eval cell: print(tool.colosseum_panel_resolve({'profile':'large-project'}))"
```
