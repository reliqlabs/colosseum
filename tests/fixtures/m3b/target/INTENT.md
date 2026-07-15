# Intent: m3b fixture crate

A stand-in behavioral contract for the benchmark-runner test. The runner does
not interpret this file; it exists so the target dir looks like a real review
target and so the dispatched prompt has an INTENT.md to reference.

## B1. Bounds

Every slice index is validated before use.

## B2. Arithmetic

Counter arithmetic is checked; no silent wrap.
