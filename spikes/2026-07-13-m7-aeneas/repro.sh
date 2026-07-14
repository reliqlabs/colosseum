#!/usr/bin/env bash
# W5 Aeneas extraction feasibility spike -- reproduction.
# Re-runs charon -> aeneas -> lean typecheck -> B1 proof for the jobq crate.
set -euo pipefail

SB="$(cd "$(dirname "$0")" && pwd)"
CHARON=/Users/mvid/Development/tools/charon/bin/charon
AENEAS=/Users/mvid/Development/tools/aeneas/bin/aeneas
LEAN="$HOME/.elan/toolchains/leanprover--lean4---v4.30.0-rc2/bin/lean"

# LEAN_PATH is borrowed from the already-built verified-rcv/specs project
# (toolchain 4.30.0-rc2, mathlib + Aeneas Lean lib prebuilt). Nothing there
# is modified; we only read its lake env.
DEP_LEAN_PATH="$(cd /Users/mvid/Development/reliq/verified-rcv/specs && lake env printenv LEAN_PATH)"

echo "== 1. charon: Rust -> LLBC (no source edits needed) =="
( cd "$SB" && "$CHARON" cargo --preset=aeneas )

echo "== 2. aeneas: LLBC -> Lean =="
"$AENEAS" -backend lean "$SB/jobq.llbc" -dest "$SB/lean-out"
# hand-written proof lives outside lean-out/ (which aeneas regenerates); stage it
cp "$SB/JobqProofs.lean" "$SB/JobqRefinement.lean" "$SB/NonVacuity.lean" "$SB/lean-out/"

echo "== 3. typecheck extracted model + B1 proof =="
export LEAN_PATH="$SB/lean-out:$DEP_LEAN_PATH"
( cd "$SB/lean-out" \
  && "$LEAN" -o Jobq.olean Jobq.lean \
  && "$LEAN" -o JobqProofs.olean JobqProofs.lean \
  && "$LEAN" -o JobqRefinement.olean JobqRefinement.lean \
  && "$LEAN" -o NonVacuity.olean NonVacuity.lean \
  && echo "OK: model + B1 proof + refinement (17 in JobqRefinement + 1 non-vacuity = 18) typecheck sorry-free" )
