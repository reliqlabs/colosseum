# Trust ledger — jobq

Claims map INTENT.md clauses to enforcing code and spec obligations. Every
citation is content-hash bound; Gate A (`check_ledger_references.py`) fails
this ledger when a cited line moves or changes, Gate B
(`check_evidence_records.py`) judges the typed evidence records against
`.fv/obligations.json`.

## B1 — bounded retries

The attempt budget branch is the sole retry decision point:
`src/queue.rs:93@sha256:0d7437f3994a` — a failed attempt within budget
retries; the branch's else arm (`src/queue.rs:98@sha256:4f9452d70d45`)
zeroes the counter and moves the job to failed, so no path increments past
`MAX_ATTEMPTS`. Spec obligation: `specs/jobq.qnt:120@sha256:a28bfefbb142`
(`inv_b1`), discharged by `quint verify`.
kani: invariants_hold_under_any_op_sequence (bounded: capacity 1..4, 10 ops, unwind 12)

## B2 — conservation

The identity is code-enforced as an inspectable predicate:
`src/queue.rs:129@sha256:64766f576744` (`conserved`), exercised after every
step of the 500-step random-walk property test. Spec obligation:
`specs/jobq.qnt:123@sha256:e5bc68821ff7` (`inv_b2`).
kani: invariants_hold_under_any_op_sequence (bounded: capacity 1..4, 10 ops, unwind 12)

## B3 — attempts track the in-flight job (biconditional)

`complete` zeroes the counter on the success path
(`src/queue.rs:82@sha256:4ea4e863b855`); the exhausted-fail path does the
same, and `start` sets it to 1, so an in-flight job always holds between 1
and `MAX_ATTEMPTS` attempts. Spec obligation (both directions):
`specs/jobq.qnt:127@sha256:66dceb0f7166` (`inv_b3`).
kani: invariants_hold_under_any_op_sequence (bounded: capacity 1..4, 10 ops, unwind 12)

## B4 — capacity

The submit guard rejects at capacity:
`src/queue.rs:57@sha256:3ffefc622e47`. Spec obligation:
`specs/jobq.qnt:131@sha256:055cbe7bb27d` (`inv_b4`), verified at capacities
2 and 4 (`--main=jobq` and `--main=jobq_c4`), constants deliberately
distinct from `MAX_ATTEMPTS` per the C7 adjudication's F6.
kani: invariants_hold_under_any_op_sequence (bounded: capacity 1..4, 10 ops, unwind 12)

## B5 — terminal monotonicity

Ghost-encoded per the C7 adjudication's F4 (a plain state invariant cannot
see across a transition; the clawback mutant proved the gap): the spec
carries the previous state's terminal counts and asserts they never
decrease. Spec obligation: `specs/jobq.qnt:134@sha256:6e5158863f11`
(`inv_mono`). Code side: no operation decrements `done` or `failed`
(`src/queue.rs:129@sha256:64766f576744` conservation plus the random-walk
property test exercise this indirectly).
kani: skipped because the ghost encoding is a spec-level obligation; the code-side counters are covered by the B1-B4 harness and the random-walk test

## W1 — liveness witness

Spec obligation: `specs/jobq.qnt:146@sha256:2fa51c3c5374` (`witness_w1`);
exhibited by seeded `quint run` witness search (simulation evidence, not
absence evidence).
kani: skipped because liveness witnesses are exhibited by trace search, not bounded proof

## W2 — failure-path witness

Spec obligation: `specs/jobq.qnt:152@sha256:e4b7245faadf`
(`witness_b1_failed`); exhibited by seeded `quint run` witness search,
added per the C7 adjudication's F7 so an unsatisfiable `fail_final` guard
can no longer keep every safety invariant green while gutting B1.
kani: skipped because liveness witnesses are exhibited by trace search, not bounded proof

## Cross-axis link

Spec-to-code conformance is established by ITF trace replay through the
real library (`../adapter/`, path-dependency on this crate) against the
default capacity-2 instance, and is labeled conformance-tested with its
trace scope; it is never a refinement claim. Error VALUES are scoped out
of replay per INTENT K3; the enforcing unit tests are the citations above.
