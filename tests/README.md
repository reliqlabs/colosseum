# Regression suite

Executable fixtures from Part IV of the remediation plan of record. Each
suite is a standalone `uv run --script` file: exit 0 pass, 1 fail, 2 when
a required toolchain is absent. `./tests/run_all.py` runs everything and
aggregates per G2 (any fail → FAILED exit 1; any suite that could not run
→ INCOMPLETE exit 3).

| Suite | Fixture | Asserts | Item |
|---|---|---|---|
| `r1_r21_r27_ledger_gates.py` | R1, R21, R27 | no vacuous ledger pass; content-hash binding catches moved/stubbed citations; axiom anchoring; per-link kani; G1 records with full binding set; G2 verdict mapping, scoped VERIFIED only | C1 |
| `r2_r5_concurrency_containment.py` | R2, R5 | citation containment (`../`, absolute, symlink, space paths); 24-writer manifest stress x3, zero losses; freshness/emptiness/reset guards | E5 |
| `r3_r4_r15_dispatch.py` | R3, R4, R15 | missing opencode → INCOMPLETE; unmatched/duplicate/traversal selections rejected; versioned event parser (truncated, malformed, error, plaintext variants) | E4 |
| `r6_manifest_failclosed.py` | R6 | zero-voice manifests invalid; all-errored wait nonzero; synthesize refuses partial evidence without override; retry history retained | E4 |
| `r7_lean_proof_gate.py` | R7 | lake build false-green demonstrated; sorry-admitted → exactly INCOMPLETE via axiom audit; no text-scan fallback | E2 |
| `r8_quint_semantics.py` | R8 | rare-path defect missed by seeded `quint run`, found by `quint verify`; evidence classes labeled at all three doc sites | E1 |
| `r9_r19_obligations.py` | R9, R19 | weakened required invariant → proposal diff (verify alone stays green); vacuous invariant, disabled transition, unreachable witness caught | E3 |
| `r10_injection_handling.py` | R10 | injection payloads contained in UNTRUSTED-REPORT delimiters; marker spoofing neutralized; skill carries data-not-instructions rule | Z3 |
| `r11_deny_first_profiles.py` | R11 | deny-first permission shape on both agent wrappers; secrets masked; phantom flag gone (live probe half lands with Z2 environment runs) | Z1 |
| `r12_preflight_scan.py` | R12 | seeded secret + escaping symlink block dispatch; worktree sheds untracked secrets; in-place mode still blocks | Z2 |
| `r13_frontmatter_validator.py` | R13 | validator green over all skills/agents/wrappers, plus known-bad self-tests | E6 |
| `r14_cli_contracts.py` | R14 | opencode/quint flag contracts and BOM version pins; flag drift fails here, not in field runs | E6 |
| `r16_r17_r18_mcp.py` | R16, R17, R18 | quint verdict parsers (Apalache-gated `unknown`, verdict/violation consistency); kani discovery of `cfg_attr`/`proof_for_contract` forms + verus library-crate command; shared `runproc` reaps the process group on timeout, retains partial output, and is used by all four CLI-backed servers; per-server smoke against fixtures | C5 |
| `r20_verdict_truth_table.py` | R20 | G2 aggregation truth table, all rows; headless pyramid runner end-to-end on a fixture crate | E4 |
| `r23_adjudication_guard.py` | R23 | G4 closure rules present; vote counts never close; contested findings retained; blinded second checks | Z4 |
| `r24_r26_conformance.py` | R24, R26 | seeded spec/code divergence caught by ITF-trace replay at the exact step; conformance-tested label carries trace scope through Gate B aggregation; REFINEMENT_VERIFIED emitted nowhere; script VERIFIEDs always scoped | C2 |
| `r25_critique_loop.py` | R25 | critique loop (cross-critique/defense/re-cross-critique) under G4; blinded re-review framing; delta attack mode invocable; mandatory holistic pass; dual spec+intent citations; run-manifest phase field | C3 |
| `r28_baseline_floors.py` | R28 | floors is a required layer under `tested`; below-floors crate (zero-test public module + missing fuzz surface) → FAILED; compliant → VERIFIED[tested]; feature-matrix combo that fails cargo check → FAILED; absent floors.json → defaults pass; cargo-fuzz absent → fuzz-time floor unmeasurable → INCOMPLETE | C8 |

Fixtures that need live model dispatch (the behavioral halves of R10, R11,
R23) are harness runs over the mechanisms tested here; they are exercised
manually, not in this suite.
