# Intent: flow fixture

A counter starts at 1 and, for ten steps, either increments or doubles.

- B1 `inv_positive`: the counter stays >= 1 in every reachable state.
- W1 `witness_reach_16`: the counter can reach exactly 16.

[ok]
test result: ok.
CONFORMANCE_TESTED: PASS
--- fv-evidence: exit=0 ---
