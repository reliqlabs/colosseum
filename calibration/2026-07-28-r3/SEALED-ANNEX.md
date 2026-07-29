# Sealed annex: calibration run 2026-07-28-r3

Held outside the repository working tree for the whole dispatch window, because
its content would reveal defect shapes to a voice that read it. Its sha256 is
committed in `PRE-REGISTRATION.md` before dispatch, so this text is provably
fixed in advance and cannot be amended after outputs are read. Published in full
with the results.

## Difficulty calibration (sealed: names defect shapes)

r1 showed a ceiling effect (3 of 4 voices at 8/8, so it did not discriminate).
r2 discriminated (7/8 and 6/8). This corpus keeps r2's hard shapes:

- One genuine concurrency defect, requiring the reviewer to reason about
  interleavings rather than read a single wrong line. Proven reachable with a
  two-thread barrier test over 2000 iterations.
- One cross-file cause/symptom split: the cause is in the token allocator, and
  it only manifests through call sites in the manager API.
- Two defects whose signature is an ABSENT error path rather than a wrong line.
  Both corresponding `LeaseError` variants are declared and never constructed
  anywhere in the crate, which is the discoverable tell.
- Two defects sit within each other's line tolerance in the same file and are
  separated only by the exact-category requirement of the match rule.

## D7 scoring note (sealed: names a defect's file)

D7's ground-truth location is the token allocator (`src/tokens.rs:27`), not the
`release()` / `reap()` call sites in `src/api.rs` where the defect becomes
observable.

**Pre-registered rule: a citation at an api.rs symptom site is a MISS.** This is
the same treatment r2 gave a right-place-wrong-category hit, and the match rule
is deliberately unchanged so the 5/8 floor stays comparable across runs.

This is defensible rather than merely strict because the fix site is unique. The
`forget()` call in `api.rs` is REQUIRED by B8, which mandates freeing
per-resource state when a lease ends. Deleting that call would trade a B4
violation for a B8 violation, so it is not a valid fix. The only change
satisfying B4 and B8 together is in the allocator: allocate from a counter that
is monotonic over the manager's lifetime while still dropping the per-resource
map entry.

Recorded so that no post-hoc adjudication is needed: had this rule been left
open, honoring an api.rs citation after seeing outputs would be exactly the
reverse-fitting that pre-registration exists to prevent.

## Why this is sealed rather than omitted

Both facts above are load-bearing parts of the design: the difficulty claim
justifies holding r2's floor, and the D7 rule must be fixed before dispatch to
keep scoring mechanical. Publishing them pre-dispatch into a tree the voices can
read would have handed over roughly half the answer key. Sealing with a
published hash keeps both properties: fixed in advance, unreadable during the
run.
