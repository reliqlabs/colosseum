# Installing Colosseum

Colosseum composes several existing verification tools through MCP wrappers. Nothing here is a self-contained product — installing Colosseum means installing the underlying tools and wiring them up so Claude Code (or any MCP-compatible client) can call them.

The setup is **incremental**: each tool is optional, and each MCP's health check reports gracefully if its underlying tool is missing. Install the layers you need; skip the ones you don't.

Tested on **macOS 14+ on Apple Silicon (M-series)**. Linux should mostly work; Windows is untested.

---

## 1. Foundational prerequisites

These are needed by almost everything else.

### 1.1 Rust

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Verus pins toolchain `1.95.0`; Charon pins a specific nightly (currently `nightly-2026-02-07`). Both will install automatically from the `rust-toolchain.toml` files when you run them.

### 1.2 Python 3.11+ and `uv`

The MCP wrappers run as `uv run --script` Python scripts with inline dependencies — no virtualenv needed.

```bash
# Python 3.11+ (macOS)
brew install python@3.12

# uv (one of)
brew install uv
# or
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1.3 JVM 17+

Required by Apalache (model checker invoked by `quint verify`). On macOS:

```bash
brew install openjdk@17
sudo ln -sfn /opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk /Library/Java/JavaVirtualMachines/openjdk-17.jdk
```

### 1.4 Native build deps for source-built tools

Only needed if you build Charon or Aeneas from source (Section 4.3 below):

```bash
brew install z3 ninja cmake opam
opam init --auto-setup        # if you haven't already
opam install dune menhir zarith easy_logging core yojson    # aeneas deps
```

### 1.5 Claude Code CLI

The primary MCP-compatible client Colosseum is designed against:

```bash
# See https://claude.com/claude-code for current install instructions
```

---

## 2. Clone the repo

```bash
git clone <your-clone-url> /Users/you/path/to/colosseum
cd /Users/you/path/to/colosseum
```

Replace the path above with wherever you want the repo to live. All examples below use `/Users/you/path/to/colosseum/` — substitute your actual path.

---

## 3. Spec-axis tools

### 3.1 Quint

Specification language for protocols and state machines.

```bash
npm install -g @informalsystems/quint
quint --version    # expect 0.32.0 or newer
```

`quint verify` will auto-download Apalache to `~/.quint/apalache` on first invocation (~250 MB, one time). Pre-warm by running `quint verify --max-steps=1 <some-spec>.qnt` once before relying on it in automation.

---

## 4. Exec-axis tools

### 4.1 Kani — bounded model checking for Rust

```bash
cargo install --locked kani-verifier
cargo-kani setup       # downloads kani-compiler binaries
cargo-kani --version   # expect 0.67.0 or newer
```

### 4.2 Verus — SMT-backed Rust verification

Use the prebuilt release on macOS arm64; source builds are also supported but slower.

```bash
mkdir -p /Users/you/path/to/tools
cd /Users/you/path/to/tools
curl -fLO https://github.com/verus-lang/verus/releases/latest/download/verus-arm64-macos.zip
# (or pick a specific tagged release from https://github.com/verus-lang/verus/releases)
unzip verus-arm64-macos.zip
mv verus-arm64-macos verus-bin
bash verus-bin/macos_allow_gatekeeper.sh   # clears Gatekeeper quarantine
verus-bin/verus --version
```

Verus bundles its own `z3`. The system `z3` you installed in 1.4 is for other tools.

### 4.3 Aeneas — Rust → Lean extraction (Charon + Aeneas)

Both build from source. **Use `gmake` on macOS**, not the system `make` 3.81.

```bash
cd /Users/you/path/to/tools

# Charon (Rust → LLBC frontend)
git clone https://github.com/AeneasVerif/charon.git
cd charon
make build           # NOT `make build-dev-bin` — that target was renamed
./bin/charon version   # subcommand, not `--version`
cd ..

# Aeneas (LLBC → Lean backend; depends on charon being in ../charon/)
git clone https://github.com/AeneasVerif/aeneas.git
cd aeneas
ln -sfn ../charon charon      # aeneas expects ./charon/ relative to itself
gmake build                   # GNU make required (`make` from Homebrew, not /usr/bin/make)
./bin/aeneas -version         # single-dash flag style
cd ..
```

**Critical config note:** Charon must be invoked with `--preset=aeneas` for output that Aeneas accepts. The MCP wrapper handles this automatically.

### 4.4 Lean 4 + Lake

Required if you want to actually prove Aeneas-extracted theorems (not just generate the Lean files). On macOS:

```bash
curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh
elan default leanprover/lean4:stable
lake --version
```

### 4.5 Lean libraries: mathlib, VCV-io, ArkLib

These are Lean libraries added to a project's `lakefile.lean`, not system installs. Configure them per-project, not globally.

**mathlib** (always needed):

```lean
require mathlib from git
  "https://github.com/leanprover-community/mathlib4.git" @ "v4.x.x"
```

**VCV-io** (foundational cryptography — adopt for any Colosseum project whose Lean tree currently has axiomatic stubs for cryptographic primitives like `encrypt`, `decrypt`, `hash`, signatures, or oracle queries):

```lean
require VCVio from git
  "https://github.com/Verified-zkEVM/VCV-io.git" @ "main"
```

VCV-io provides:
- `OracleComp spec α` — free monad over oracle queries; replaces axiomatic primitive functions with mechanically-modelled oracle interactions
- `ProbComp α` — probabilistic computations with SPMF semantics
- `evalDist` / `Pr[= x | comp]` / `Pr[p | comp]` — distribution and event probabilities
- Relational program logic with `by_equiv`, `by_hoare`, `rvcstep`, `rvcgen`, `game_trans` tactics
- `LatticeCrypto` sublibrary: NIST PQC primitives (ML-DSA, ML-KEM, Falcon) with both proofs and executable implementations

**ArkLib** (SNARK / IOR foundations — only needed if your project uses FRI-style, Spartan, Sum-check, STIR, WHIR, or Binius proof systems):

```lean
require ArkLib from git
  "https://github.com/Verified-zkEVM/ArkLib.git" @ "main"
```

ArkLib does **not** currently cover Groth16, PLONK, or classical STARKs. If your zk path is Groth16-based (e.g. zkdcap), VCV-io alone is the right substrate today.

After updating `lakefile.lean`, run `lake update && lake build` to fetch and compile.

---

## 5. Register the MCPs with Claude Code

Each MCP is a Python script that wraps one underlying tool. Register them all (or just the ones for tools you installed):

```bash
COLOSSEUM=/Users/you/path/to/colosseum

claude mcp add -s user kani -- $COLOSSEUM/mcp/kani-mcp/kani_mcp.py
claude mcp add -s user quint -- $COLOSSEUM/mcp/quint-mcp/quint_mcp.py
claude mcp add -s user goedel -- $COLOSSEUM/mcp/goedel-mcp/goedel_mcp.py
claude mcp add -s user lm-studio -- $COLOSSEUM/mcp/lm-studio-mcp/lm_studio_mcp.py
claude mcp add -s user external-model -- $COLOSSEUM/mcp/external-model-mcp/external_model_mcp.py

# Verus + Aeneas need env vars pointing at the binaries you installed in §4
claude mcp add -s user verus \
  --env VERUS_BIN=/Users/you/path/to/tools/verus-bin/verus \
  -- $COLOSSEUM/mcp/verus-mcp/verus_mcp.py

claude mcp add -s user aeneas \
  --env CHARON_BIN=/Users/you/path/to/tools/charon/bin/charon \
  --env AENEAS_BIN=/Users/you/path/to/tools/aeneas/bin/aeneas \
  -- $COLOSSEUM/mcp/aeneas-mcp/aeneas_mcp.py
```

Verify:

```bash
claude mcp list
# expect ✓ Connected for each colosseum MCP
```

Restart Claude Code so the new MCPs load into a session.

---

## 6. Optional: local model layer

For the multi-model adversarial layer's local floor (free, always-on diversity), install [LM Studio](https://lmstudio.ai):

1. Install LM Studio and load at least one general-purpose model. Recommended pairs for adversarial diversity:
   - Qwen 3.6 (any size) + Gemma 3 / 4 (any size) — different families
   - Add Goedel-Prover-V2-32B if you want the Lean tactic specialist
2. Enable the **Developer** tab → **Server** → start on the default port (`1234`).
3. Confirm: `curl http://localhost:1234/v1/models` should list your loaded models.

The `lm-studio-mcp` and `goedel-mcp` MCPs will auto-detect. No re-registration needed.

**Known caveat (reasoning-mode models):** modern frontier-style local models (Qwen 3+, Gemma 4+) default to thinking-mode and silently consume the entire `max_tokens` budget on hidden chain-of-thought. For adversarial use, pass `max_tokens` of 65536 or higher to leave room for visible output after reasoning. Documented in `mcp/lm-studio-mcp/README.md`.

---

## 7. OpenCode CLI + providers (canonical adversarial dispatch path)

The Mode 1 dispatch path described in `skills/colosseum-adversarial/SKILL.md` runs `opencode run --agent spec-adversary --model <voice> --variant max` once per (voice, slice) pair. This is the **primary** dispatch surface for multi-voice adversarial work; the MCP channel in Section 8 is the fallback for hosts where OpenCode can't be installed.

### 7.1 Install OpenCode CLI

```bash
brew install sst/tap/opencode    # or see https://opencode.ai for other platforms
opencode --version               # verify
```

### 7.2 Configure providers

Provider definitions live in `~/.config/opencode/opencode.jsonc`. The canonical 5-voice panel needs these providers configured (the fifth voice, Claude, runs in-harness via the Agent subagent and needs no OpenCode entry):

```jsonc
{
  "provider": {
    // Gateway-routed frontier voices (single credential, multiple models)
    "burnt": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Burnt AI Gateway",
      "options": {
        "baseURL": "https://<your-gateway-host>/v1",
        "apiKey": "<gateway-api-key>"
      },
      "models": {
        "cloudflare-100/@cf/moonshotai/kimi-k2.6": {
          "name": "kimi-k2.6",
          "tool_call": true,
          "reasoning": false,
          "limit": { "context": 128000, "output": 131072 }
        },
        "cloudflare-100/@cf/nvidia/nemotron-3-120b-a12b": {
          "name": "nemotron-3-120b-a12b",
          "tool_call": true,
          "reasoning": true,
          "limit": { "context": 128000, "output": 131072 },
          "variants": { "max": { "reasoningEffort": "high" } }
        },
        "cloudflare-100/@cf/openai/gpt-oss-120b": {
          "name": "gpt-oss-120b",
          "tool_call": true,
          "reasoning": false,
          "limit": { "context": 128000, "output": 131072 }
        }
        // ... add other gateway routes per `curl <baseURL>/models`. Verify periodically; operator roster drifts. Claude and Gemini are NOT in the Burnt gateway — use direct openai/google providers and in-harness claude-agent.
      }
    },

    // Local DeepSeek V4 Flash via DwarfStar4 runner
    "ds4": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "DwarfStar4 (local)",
      "options": { "baseURL": "http://127.0.0.1:8000/v1" },
      "models": {
        "deepseek-v4-flash": {
          "name": "DeepSeek V4 Flash",
          "tool_call": true,
          "reasoning": true,
          "limit": { "context": 400000, "output": 32768 },
          "variants": { "max": { "reasoningEffort": "high" } }
        }
      }
    },

    // OpenAI direct (canonical ChatGPT voice)
    "openai": {
      "npm": "@ai-sdk/openai",
      "name": "OpenAI (direct)",
      "options": { "apiKey": "{env:OPENAI_API_KEY}" },
      "models": {
        "gpt-5.1-thinking": {
          "name": "GPT-5.1 (thinking)",
          "tool_call": true,
          "reasoning": true,
          "limit": { "context": 400000, "output": 131072 },
          "variants": {
            "high": { "reasoningEffort": "high" },
            "max": { "reasoningEffort": "high" }
          }
        }
      }
    },

    // Google Gemini direct (canonical Gemini voice)
    "google": {
      "npm": "@ai-sdk/google",
      "name": "Google Gemini (direct)",
      "options": { "apiKey": "{env:GOOGLE_GENERATIVE_AI_API_KEY}" },
      "models": {
        "gemini-3-pro": {
          "name": "Gemini 3 Pro",
          "tool_call": true,
          "reasoning": true,
          "limit": { "context": 2000000, "output": 65536 },
          "variants": {
            "high": { "reasoningEffort": "high" },
            "max": { "reasoningEffort": "high" }
          }
        }
      }
    },

    // Local LM Studio voices (free family-diversity layer)
    "lmstudio": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "LM Studio (local)",
      "options": { "baseURL": "http://127.0.0.1:1234/v1" },
      "models": {
        "leanstral-2603": { "name": "Leanstral 2603" }
        // ... per your loaded model list
      }
    }
  }
}
```

Set `OPENAI_API_KEY` and `GOOGLE_GENERATIVE_AI_API_KEY` in your shell environment (or directly in `opencode.jsonc` if you prefer hardcoded keys to env interpolation). Verify the model IDs against the providers' current docs — `gpt-5.1-thinking` and `gemini-3-pro` are pinned as of writing but provider model IDs drift; run `opencode models openai` and `opencode models google` to confirm.

Verify with `opencode run --model openai/gpt-5.1-thinking "say hi"` and similar one-shot probes per provider before relying on the dispatch script.

## 8. Optional: cloud model layer via external-model-mcp (Mode 3 fallback only)

`external-model-mcp` exposes three provider channels — `query_openai` (OpenAI BYOK), `query_google` (Google BYOK), and `query_gateway` (operator-curated multi-model gateway). These are the **Mode 3 fallback** dispatch path used only when OpenCode is not installed on the host. For routine adversarial work use Section 7 above (OpenCode CLI), not this MCP.

The MCP loads credentials from `.env` files (gitignored) following this search order: `$COLOSSEUM_DOTENV` override → `$CWD/.env` → `<colosseum-repo-root>/.env` → `~/.colosseum.env`. Setting env vars on the MCP launch line still works as before; the `.env` path is operationally cleaner.

For BYOK across Claude + GPT + Gemini:

```bash
claude mcp remove -s user external-model

claude mcp add -s user external-model \
  --env OPENAI_API_KEY=sk-... \
  --env GEMINI_API_KEY=... \
  -- $COLOSSEUM/mcp/external-model-mcp/external_model_mcp.py
```

For the **gateway** channel (one credential, multiple models including non-Western frontier voices like kimi-k2-6, glm-4-7-flash, gpt-oss-120b):

```bash
# Drop credentials into <colosseum-repo-root>/.env (gitignored). Example:
cat >> $COLOSSEUM/.env <<EOF
COLOSSEUM_GATEWAY_BASE_URL=https://your-gateway-host/v1
COLOSSEUM_GATEWAY_API_KEY=xxx
COLOSSEUM_GATEWAY_DEFAULT_MODEL=claude-opus-4-7
EOF

# Restart the MCP / Claude Code session so the env is picked up.
```

The gateway is operator-curated; the model list drifts. Pin model IDs in adversarial-pass artifacts (see `skills/colosseum-adversarial/SKILL.md` dispatch section for the gateway-route caveats and per-route failure-mode notes).

Any single credential channel works alone; using all three gives maximum coverage.

---

## 9. Verify the full install

From a fresh Claude Code session, call each MCP's health check. Expected: `ok: true` for tools you installed, graceful "not installed" for tools you skipped.

```
mcp__kani__check_kani_health()
mcp__quint__check_quint_health()
mcp__verus__check_verus_health()
mcp__aeneas__check_aeneas_health()
mcp__goedel__check_goedel_health()
mcp__lm-studio__check_lmstudio_health()
mcp__external-model__check_external_health()
```

---

## 10. Optional: load the skills and agents into Claude Code

The MCPs cover the verification tools. The Colosseum **skills** (`colosseum-intent`, `colosseum-adversarial`, `colosseum-verify`, `colosseum-compose`, `colosseum-change`, `colosseum-reverse-intent`) and **agents** (`colosseum-spec-adversary`, `colosseum-failure-classifier`) need to be made discoverable to Claude Code by symlinking into your user config:

```bash
mkdir -p ~/.claude/skills ~/.claude/agents
ln -s $COLOSSEUM/skills/colosseum-* ~/.claude/skills/
ln -s $COLOSSEUM/agents/colosseum-* ~/.claude/agents/
```

Alternatively, for project-local use only, symlink into `.claude/skills/` and `.claude/agents/` within the project you're verifying.

---

## 11. Troubleshooting

**`charon: error: unexpected argument '--version'`** — Charon uses subcommand syntax. Use `charon version`.

**`aeneas: unknown option '--version'`** — Aeneas uses single-dash. Use `aeneas -version`.

**`aeneas: Invalid option detected: the serialized crate was generated by Charon without the --preset=aeneas option`** — The MCP wrapper handles this; if you call charon directly, add `--preset=aeneas`.

**`make: *** No rule to make target 'build-dev-bin'`** — Charon's Makefile target is `build` (or `build-dev`), not `build-dev-bin`.

**`You seem to be using the OSX antiquated Make version`** — Aeneas needs GNU make 4+. Install via `brew install make` and invoke as `gmake`.

**LM Studio returns empty `text` field with `reasoning_tokens` set high** — reasoning-mode model consumed entire budget. Raise `max_tokens` to 65536+ for adversarial work, or disable thinking via provider-specific extra params if exposed.

**Apalache hangs on first `quint verify`** — first call downloads ~250 MB. Run it once manually outside automation to let the download complete.

**Verus binary won't run on macOS** — run the bundled gatekeeper-clearing script: `bash verus-bin/macos_allow_gatekeeper.sh`.

**MCP shows `✓ Connected` but tools aren't callable in Claude Code** — restart Claude Code; MCPs are loaded at session start.

---

## What you DON'T need

Colosseum is methodology + wrappers; the verification tools themselves are independent of it. You can use any subset:

- Just want Kani + property tests? Install §1.1, §1.2, §1.5, §4.1, register `kani-mcp` from §5.
- Just want the spec-axis (Quint)? §1.1, §1.2, §1.3, §1.5, §3.1, register `quint-mcp`.
- Just want adversarial spec review? §1.1, §1.2, §1.5, §6 (local) or §7 (cloud), register the model MCPs.

Each MCP's health check tells you what's installed; the pyramid skill (`colosseum-verify`) gracefully skips layers whose tools aren't available.
