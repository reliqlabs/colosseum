#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
check_evidence_records — the SEMANTIC evidence gate (Gate B of the
two-gate ledger split, C1; contracts G1/G2).

Gate A (`check_ledger_references.py`) checks that the ledger's references
hook into live code. This gate checks the claims themselves: every claim
the assurance profile requires is backed by a typed G1 record carrying
the full binding set, and the run-level verdict follows the G2 truth
table exactly. Prose never passes this gate; only records do.

RECORD SCHEMA (JSON; one file with a list, or a directory of *.json)

    {
      "claim_id": "B1",              # stable intent clause ID (B/S/T)
      "required": true,              # per the active assurance profile
      "evidence_class": "bounded-checked",
          # code-enforced | proof-discharged | bounded-checked |
          # test-witnessed | conformance-tested | externally-assumed |
          # unverified
      "result": "PASS",              # PASS | FAIL | INCOMPLETE
      "scope": "safety under bound 10, Apalache 0.56.1",
      "bindings": {
        "source_snapshot":        "<commit>+<dirty-tree content hash>",
        "intent_hash":            "<sha256>",
        "obligation_manifest_hash": "<sha256>",
        "profile":                "bounded",
        "required_targets":       ["B1", "B2", "W1"],
        "environment_policy":     "z2-worktree",
        "toolchain_digests":      {"quint": "0.32.0"},
        "command":                "quint verify --invariant=... main.qnt",
        "configuration":          {"max_steps": 10},
        "seeds":                  "0x1",        # null allowed, key required
        "raw_output_hash":        "<sha256>",
        "parser_schema_version":  "opencode-events-v1",
        "run_id":                 "intent-v1-2026-07-11T000000Z"
      },
      "waiver": null   # key REQUIRED; a waiver object or null, never absent
    }

A record missing ANY field above — including any bindings subfield and
the waiver key — is rejected (R27). `evidence_class` and `result` are
orthogonal: a `bounded-checked` record may FAIL, an `unverified` record
may not PASS silently.

VERDICT (G2 truth table; exit code)
    FAILED       (1)  any required claim has a valid record with result FAIL
    INCOMPLETE   (3)  any required claim is missing a record, or its record
                      is invalid/stale/INCOMPLETE, or rests on
                      externally-assumed/unverified evidence without a
                      waiver, or the required-claims list is empty
    VERIFIED[..] (0)  every required claim PASSes under a named profile;
                      the scope string names the profile and every waived
                      or externally-assumed claim — never bare VERIFIED
    ERROR        (2)  unreadable records / usage errors

USAGE
    check_evidence_records.py --records <file.json|dir> \\
        --require B1,B2,W1 [--expect-snapshot <prefix>] [--json]

    --require names the claim IDs the active profile requires (or pass
    --manifest <obligations.json> to derive them from an E3 obligation
    manifest's invariant/witness IDs). --expect-snapshot rejects records
    bound to a different source snapshot as stale.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EVIDENCE_CLASSES = {
    "code-enforced", "proof-discharged", "bounded-checked", "test-witnessed",
    "conformance-tested", "externally-assumed", "unverified",
}
RESULTS = {"PASS", "FAIL", "INCOMPLETE"}
TOP_FIELDS = ("claim_id", "required", "evidence_class", "result", "scope",
              "bindings", "waiver")
BINDING_FIELDS = (
    "source_snapshot", "intent_hash", "obligation_manifest_hash", "profile",
    "required_targets", "environment_policy", "toolchain_digests", "command",
    "configuration", "seeds", "raw_output_hash", "parser_schema_version",
    "run_id",
)
# Keys whose value may be null (the key itself is still mandatory).
NULLABLE = {"seeds", "waiver"}


def validate_record(rec: dict, expect_snapshot: str | None) -> list[str]:
    """Returns the list of defects; empty means the record is valid."""
    defects = []
    for field in TOP_FIELDS:
        if field not in rec:
            defects.append(f"missing field {field!r}")
    if defects:
        return defects
    if rec["evidence_class"] not in EVIDENCE_CLASSES:
        defects.append(f"unknown evidence_class {rec['evidence_class']!r}")
    if rec["result"] not in RESULTS:
        defects.append(f"unknown result {rec['result']!r}")
    if not isinstance(rec["scope"], str) or not rec["scope"].strip():
        defects.append("scope is empty")
    bindings = rec["bindings"]
    if not isinstance(bindings, dict):
        defects.append("bindings is not an object")
        return defects
    for field in BINDING_FIELDS:
        if field not in bindings:
            defects.append(f"missing binding field {field!r}")
        elif bindings[field] in ("", [], {}) or \
                (bindings[field] is None and field not in NULLABLE):
            defects.append(f"empty binding field {field!r}")
    if expect_snapshot and isinstance(bindings.get("source_snapshot"), str) \
            and not bindings["source_snapshot"].startswith(expect_snapshot):
        defects.append(
            f"stale record: bound to snapshot {bindings['source_snapshot']!r}, "
            f"expected {expect_snapshot!r}"
        )
    return defects


def unwrap(data: object) -> list[dict]:
    """Flatten one JSON payload to a list of record objects. A bare list or
    a bare single record is unversioned (v0). An object carrying a `records`
    key is the M5 versioned ledger envelope
    (`{"ledger_schema_version": ..., "records": [...]}`); unwrap it. The
    version field itself is not validated here (that is
    check_ledger_version.py's job); this reader only accepts either shape so
    a versioned ledger and its equivalent bare list gate identically."""
    if isinstance(data, dict) and "records" in data:
        data = data["records"]
    if isinstance(data, list):
        return data
    return [data]


def load_records(path: Path) -> list[dict]:
    if path.is_dir():
        records = []
        for p in sorted(path.glob("*.json")):
            records.extend(unwrap(json.loads(p.read_text())))
        return records
    return unwrap(json.loads(path.read_text()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True, type=Path)
    ap.add_argument("--require", default=None,
                    help="comma-separated claim IDs the profile requires")
    ap.add_argument("--manifest", type=Path, default=None,
                    help="derive required claim IDs from an obligation manifest")
    ap.add_argument("--expect-snapshot", default=None,
                    help="reject records bound to a different source snapshot")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        records = load_records(args.records)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read records: {e}", file=sys.stderr)
        print("\nVERDICT: ERROR", file=sys.stderr)
        return 2

    required: list[str] = []
    if args.require:
        required = [c.strip() for c in args.require.split(",") if c.strip()]
    elif args.manifest:
        try:
            manifest = json.loads(args.manifest.read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERROR: cannot read manifest: {e}", file=sys.stderr)
            print("\nVERDICT: ERROR", file=sys.stderr)
            return 2
        required = [x["id"] for x in manifest.get("invariants", [])] + \
                   [x["id"] for x in manifest.get("witnesses", [])]
    else:
        print("ERROR: pass --require or --manifest — a gate with no required "
              "claims gates nothing", file=sys.stderr)
        print("\nVERDICT: ERROR", file=sys.stderr)
        return 2

    by_claim: dict[str, dict] = {}
    per_claim: list[dict] = []
    for rec in records:
        cid = rec.get("claim_id")
        if isinstance(cid, str):
            by_claim[cid] = rec

    failed: list[str] = []
    incomplete: list[str] = []
    assumed_or_waived: list[str] = []

    if not required:
        incomplete.append("(required-claims list is empty — invalid run)")

    for cid in required:
        rec = by_claim.get(cid)
        if rec is None:
            incomplete.append(f"{cid}: no record")
            per_claim.append({"claim_id": cid, "status": "missing-record"})
            continue
        defects = validate_record(rec, args.expect_snapshot)
        if defects:
            incomplete.append(f"{cid}: invalid record ({'; '.join(defects)})")
            per_claim.append({"claim_id": cid, "status": "invalid",
                              "defects": defects})
            continue
        klass, result = rec["evidence_class"], rec["result"]
        if result == "FAIL":
            failed.append(f"{cid}: {klass} FAIL — {rec['scope']}")
            per_claim.append({"claim_id": cid, "status": "FAIL",
                              "evidence_class": klass})
            continue
        if result == "INCOMPLETE":
            incomplete.append(f"{cid}: record result INCOMPLETE")
            per_claim.append({"claim_id": cid, "status": "INCOMPLETE",
                              "evidence_class": klass})
            continue
        # result == PASS
        if klass in ("externally-assumed", "unverified"):
            if rec["waiver"]:
                assumed_or_waived.append(cid)
                per_claim.append({"claim_id": cid, "status": "PASS-waived",
                                  "evidence_class": klass})
            else:
                incomplete.append(
                    f"{cid}: {klass} evidence cannot PASS without a waiver")
                per_claim.append({"claim_id": cid, "status": "unwaived-assumption",
                                  "evidence_class": klass})
            continue
        if rec["waiver"]:
            assumed_or_waived.append(cid)
        per_claim.append({"claim_id": cid, "status": "PASS",
                          "evidence_class": klass, "scope": rec["scope"]})

    if failed:
        verdict, code = "FAILED", 1
    elif incomplete:
        verdict, code = "INCOMPLETE", 3
    else:
        profiles = {by_claim[c]["bindings"]["profile"] for c in required}
        scope = f"profile={'/'.join(sorted(profiles))}"
        if assumed_or_waived:
            scope += f"; waived-or-assumed={','.join(sorted(assumed_or_waived))}"
        verdict, code = f"VERIFIED[{scope}]", 0

    report = {
        "gate": "semantic-evidence",
        "records": str(args.records),
        "required_claims": required,
        "per_claim": per_claim,
        "failed": failed,
        "incomplete": incomplete,
        "verdict": verdict,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for entry in per_claim:
            print(f"  [{entry['status']:>18}] {entry['claim_id']} "
                  f"({entry.get('evidence_class', '-')})")
        for msg in failed + incomplete:
            print(f"  ! {msg}")
    print(f"\nVERDICT: {verdict}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
