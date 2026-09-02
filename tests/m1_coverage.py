#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
M1 — coverage dashboard, sourced from typed G1 evidence, G2-conformant (M1).

coverage_dashboard.py renders a per-required-claim coverage view over G1
evidence records: it is not a gate, but its own surface must never violate
G2 — no unqualified "VERIFIED" token, ever. This suite exercises the
dashboard against a fixture set covering every claim disposition (PASS,
FAIL, INCOMPLETE, missing-record, waived assumption, unwaived assumption),
checks coverage counts and the per-evidence_class breakdown, checks the
run-level verdict against the G2 truth table, checks `--check` catches
its own would-be violations (proven directly against the token-discipline
regex, not just trivially green on already-clean fixtures), and checks
the M5 versioned-envelope input shape is accepted identically to a bare
list.

No external toolchain required. Exit 0 pass, 1 fail.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DASHBOARD = REPO / "scripts" / "coverage_dashboard.py"
FIXTURES = REPO / "tests" / "fixtures" / "m1"
FAILURES: list[str] = []

ALL_CLAIMS = "B1,B2,B3,B4,W1,S1"

# Mirrors the dashboard's own BARE_VERIFIED regex. Kept independent here
# so this suite proves the token-discipline rule itself, not just that
# --check happens to pass on inputs that were never going to trip it.
BARE_VERIFIED = re.compile(r"VERIFIED(?!\[)")


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def run(records: Path, *extra: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["uv", "run", "--script", str(DASHBOARD), "--records", str(records), *extra],
        capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def run_json(records: Path, *extra: str) -> tuple[int, dict, str]:
    code, out, err = run(records, "--json", *extra)
    try:
        payload = json.loads(out)
    except json.JSONDecodeError as e:
        return code, {"_parse_error": str(e), "_stdout": out}, err
    return code, payload, err


def row(dashboard: dict, claim_id: str) -> dict:
    for r in dashboard["rows"]:
        if r["claim_id"] == claim_id:
            return r
    raise KeyError(claim_id)


def main() -> int:
    records = FIXTURES / "records.json"
    envelope = FIXTURES / "records-envelope.json"
    records_dir = FIXTURES / "records_dir"
    manifest = FIXTURES / "obligations.json"
    manifest_empty = FIXTURES / "obligations-empty.json"

    # ── (a) coverage counts + per-class breakdown, mixed fixture ────────
    code, d, err = run_json(records, "--require", ALL_CLAIMS)
    mixed_code = code
    check("mixed set: exit 1 (FAILED, a required claim FAILs)", code == 1)
    s = d.get("summary", {})
    check("mixed set: total_required == 6", s.get("total_required") == 6)
    check("mixed set: pass == 2 (B1, W1)", s.get("pass") == 2)
    check("mixed set: fail == 1 (B2)", s.get("fail") == 1)
    check("mixed set: incomplete == 1 (B3)", s.get("incomplete") == 1)
    check("mixed set: missing == 1 (B4)", s.get("missing") == 1)
    check("mixed set: invalid == 0", s.get("invalid") == 0)
    check("mixed set: unwaived_assumption == 1 (S1)",
          s.get("unwaived_assumption") == 1)
    check("mixed set: waived_or_assumed == ['W1']",
          s.get("waived_or_assumed") == ["W1"])
    by_class = s.get("by_evidence_class", {})
    check("per-class: bounded-checked pass=1 fail=1",
          by_class.get("bounded-checked") == {"pass": 1, "fail": 1, "incomplete": 0, "other": 0})
    check("per-class: test-witnessed incomplete=1",
          by_class.get("test-witnessed") == {"pass": 0, "fail": 0, "incomplete": 1, "other": 0})
    check("per-class: externally-assumed pass=1 (waived)",
          by_class.get("externally-assumed") == {"pass": 1, "fail": 0, "incomplete": 0, "other": 0})
    check("per-class: unverified other=1 (unwaived assumption, not a pass)",
          by_class.get("unverified") == {"pass": 0, "fail": 0, "incomplete": 0, "other": 1})

    # ── (b) missing required claims surface as gaps ─────────────────────
    b4 = row(d, "B4")
    check("B4 (no record) -> status missing-record", b4["status"] == "missing-record")
    check("B4 gap row carries no evidence_class", b4["evidence_class"] is None)
    s1 = row(d, "S1")
    check("S1 (unverified PASS, no waiver) -> status unwaived-assumption, not PASS",
          s1["status"] == "unwaived-assumption")
    w1 = row(d, "W1")
    check("W1 (externally-assumed PASS, waived) -> status PASS, waived=true",
          w1["status"] == "PASS" and w1["waived"] is True)

    # ── (c) verdict matches G2 truth table ───────────────────────────────
    check("mixed set verdict is exactly 'FAILED'", d.get("verdict") == "FAILED")

    code, d2, err2 = run_json(records, "--require", "B1,W1")
    check("all-PASS subset (B1,W1): exit 0", code == 0)
    check("all-PASS subset: verdict is scoped VERIFIED[...]",
          d2.get("verdict", "").startswith("VERIFIED[")
          and d2.get("verdict") == "VERIFIED[profile=bounded] (waived: W1)")
    check("all-PASS subset: verdict is never bare VERIFIED",
          not BARE_VERIFIED.search(d2.get("verdict", "")))

    code, _, err3 = run(records, "--require", "B2")
    check("FAIL-only claim -> exit 1", code == 1)
    check("FAIL-only claim -> stderr verdict FAILED", "VERDICT: FAILED" in err3)

    code, _, err4 = run(records, "--require", "B4")
    check("missing-only claim -> exit 3", code == 3)
    check("missing-only claim -> stderr verdict INCOMPLETE", "VERDICT: INCOMPLETE" in err4)

    code, _, err5 = run(records, "--manifest", str(manifest_empty))
    check("empty manifest (no invariants/witnesses) -> exit 3 INCOMPLETE",
          code == 3 and "VERDICT: INCOMPLETE" in err5)

    code, _, err6 = run(records, "--require", "")
    check("--require '' (no claim set named at all) -> exit 2, an error not a pass",
          code == 2)

    # ── stdout hygiene: --json stdout is pure JSON, nothing else ────────
    code, out_json, _ = run(records, "--require", ALL_CLAIMS, "--json")
    try:
        json.loads(out_json)
        clean_json_stdout = True
    except json.JSONDecodeError:
        clean_json_stdout = False
    check("--json stdout parses as JSON with no stray progress lines",
          clean_json_stdout)
    check("--json stdout never contains the literal token 'VERDICT:' "
          "(that's stderr-only)", "VERDICT:" not in out_json)

    # ── (d) --check passes on the dashboard's own output, every fixture ─
    for label, require_arg in (
        ("mixed set", ALL_CLAIMS),
        ("all-PASS subset", "B1,W1"),
        ("FAIL-only", "B2"),
        ("missing-only", "B4"),
    ):
        code, out, err = run(records, "--require", require_arg, "--check")
        check(f"--check clean on {label}", code == 0 and "CHECK: clean" in err)

    # ── (e) prove --check's underlying mechanism actually catches a leak
    # by asserting the token-discipline regex directly: it must flag a
    # bare VERIFIED and must NOT flag a properly scoped one. This is the
    # control that shows a real violation would be caught, not merely
    # that clean fixtures stay clean.
    check("token discipline: bare 'VERDICT: VERIFIED' IS flagged",
          bool(BARE_VERIFIED.search("VERDICT: VERIFIED")))
    check("token discipline: trailing bare VERIFIED IS flagged",
          bool(BARE_VERIFIED.search("some prose says VERIFIED here")))
    check("token discipline: scoped 'VERIFIED[profile=bounded]' is NOT flagged",
          not BARE_VERIFIED.search("VERDICT: VERIFIED[profile=bounded]"))
    check("token discipline: scoped with visible waiver suffix is NOT flagged",
          not BARE_VERIFIED.search(
              "VERIFIED[profile=bounded] (waived: W1)"))
    # cross-check against every line the dashboard actually emits for the
    # all-PASS fixture, across text, stderr, and --json renderings: the
    # word VERIFIED must appear at least once (it's the real verdict) and
    # every occurrence must be immediately followed by '['.
    code, text_out, text_err = run(records, "--require", "B1,W1")
    _, json_out, json_err = run(records, "--require", "B1,W1", "--json")
    combined = "\n".join([text_out, text_err, json_out, json_err])
    verified_occurrences = [m.start() for m in re.finditer("VERIFIED", combined)]
    check("dashboard output actually contains VERIFIED at least once "
          "(the check above isn't vacuous)", len(verified_occurrences) > 0)
    check("every VERIFIED occurrence in real output is immediately scoped",
          not BARE_VERIFIED.search(combined))

    # ── (f) versioned envelope accepted, equals bare-list result ────────
    code_env, d_env, _ = run_json(envelope, "--require", ALL_CLAIMS)
    check("versioned envelope: exit code matches bare-list",
          code_env == mixed_code and code_env == 1)
    d_env_norm = dict(d_env)
    d_env_norm["records"] = str(records)  # only the echoed input path differs
    check("versioned envelope: dashboard payload identical to bare-list input",
          d_env_norm == d)

    # ── directory loading + --manifest derivation (bonus coverage) ──────
    code, d_dir, _ = run_json(records_dir, "--require", "B1,B2,B3,W1,S1")
    check("directory of *.json records loads and aggregates", code == 1
          and d_dir.get("summary", {}).get("total_required") == 5)

    code, d_man, _ = run_json(records, "--manifest", str(manifest))
    check("--manifest derives required IDs from invariants[]+witnesses[]",
          d_man.get("required_claims") == ["B1", "B2", "B3", "B4", "W1", "S1"])

    # ── (g) no drift from the semantic gate ─────────────────────────────
    # The dashboard mirrors check_evidence_records.py's validator and G2
    # verdict logic. Run both on identical inputs and require the verdicts
    # to agree, so a future change to the gate that isn't mirrored here
    # fails loudly instead of drifting silently.
    gate = REPO / "scripts" / "check_evidence_records.py"

    def gate_verdict(*extra: str) -> str:
        gate_extra = [*extra]
        if "--manifest" in gate_extra:
            gate_extra += ["--expect-manifest", "2" * 64]
        proc = subprocess.run(
            ["uv", "run", "--script", str(gate), "--records", str(records),
             "--allow-unbound", *gate_extra, "--json"],
            capture_output=True, text=True, timeout=60)
        try:
            return json.loads(proc.stdout)["verdict"]
        except (json.JSONDecodeError, KeyError):
            return f"<gate-error rc={proc.returncode}>"

    for label, extra in (("mixed", ["--require", ALL_CLAIMS]),
                         ("all-PASS", ["--require", "B1,W1"]),
                         ("FAIL-only", ["--require", "B2"]),
                         ("missing-only", ["--require", "B4"]),
                         ("via-manifest", ["--manifest", str(manifest)])):
        _, dj, _ = run_json(records, *extra)
        gv = gate_verdict(*extra)
        check(f"no drift vs semantic gate ({label})",
              dj.get("verdict") == gv,
              f"dashboard={dj.get('verdict')} gate={gv}")

    print()
    if FAILURES:
        print(f"M1: {len(FAILURES)} failure(s)")
        return 1
    print("M1: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
