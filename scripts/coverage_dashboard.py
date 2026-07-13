#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
coverage_dashboard — a per-claim coverage view over G1 evidence records
(M1; contracts G1/G2).

Gate B (`check_evidence_records.py`) answers one question per run: does
every required claim PASS. This tool answers the question underneath
that one: for each required claim, what evidence backs it, at what
evidence_class, with what result, waived or not — and which required
claims have no record at all. It is a read-only view, not a gate: it
renders the same G1 records Gate B would consume and computes the same
G2 verdict, but its purpose is visibility into coverage, not enforcement.

RECORD SCHEMA — identical to check_evidence_records.py (see that file's
docstring for the full field list). This tool additionally accepts the
M5 forward-compat versioned envelope: a top-level JSON object carrying a
`records` key, e.g. `{"ledger_schema_version": "...", "records": [...]}`.
A bare list or a bare single record object is treated as unversioned.

G2 HONESTY (this tool's own conformance obligation)

Per G2, "VERIFIED" is never a bare token; it always carries a scope,
e.g. `VERIFIED[profile=bounded; waived-or-assumed=W1]`. Individual claim
rows never render as "verified" either — a claim's row shows its
evidence_class and result (PASS/FAIL/INCOMPLETE/missing-record/invalid/
unwaived-assumption), never an unqualified verdict word. `--check` scans
this tool's own rendered output (table, verdict banner, and JSON payload)
and exits nonzero if a bare `VERIFIED` (not immediately followed by `[`)
would ever appear — the R26-style self-conformance guarantee applied to
the dashboard surface itself.

VERDICT (same G2 truth table as check_evidence_records.py; exit code)
    FAILED       (1)  any required claim has a valid record with result FAIL
    INCOMPLETE   (3)  any required claim is missing a record, or its record
                      is invalid, or its record result is INCOMPLETE, or it
                      rests on externally-assumed/unverified evidence
                      without a waiver, or the required-claims list is empty
    VERIFIED[..] (0)  every required claim PASSes; scope names the profile
                      and every waived or externally-assumed claim
    ERROR        (2)  unreadable records/manifest, or neither --require nor
                      --manifest given

USAGE
    coverage_dashboard.py --records <file.json|dir> \\
        --require B1,B2,W1 [--json]
    coverage_dashboard.py --records <file.json|dir> \\
        --manifest <obligations.json> [--json]
    coverage_dashboard.py --records <file.json|dir> --require B1,W1 --check

--require names the claim IDs the active profile requires (or pass
--manifest <obligations.json> to derive them from an E3 obligation
manifest's invariant/witness IDs). --json prints the structured dashboard
to stdout with nothing else on stdout; text mode prints a readable table
to stdout. In both modes the verdict banner goes to stderr only.
--check runs in self-conformance mode: it prints CHECK: ... to stderr and
exits 0 if the rendered output is clean, 1 if a bare VERIFIED leaked.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EVIDENCE_CLASSES = {
    "code-enforced", "proof-discharged", "bounded-checked", "test-witnessed",
    "conformance-tested", "externally-assumed", "unverified",
}
RESULTS = {"PASS", "FAIL", "INCOMPLETE"}
ASSUMED_CLASSES = {"externally-assumed", "unverified"}
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

# Per-claim statuses that mean the claim is not covered by a passing
# record. Drives both the run verdict and the "incomplete" summary bucket.
GAP_STATUSES = {"missing-record", "invalid", "INCOMPLETE", "unwaived-assumption"}

UNSCOPED_VERDICT_RE = re.compile(r"VERIFIED(?!\[)")  # a bare, unqualified verdict


def validate_record(rec: dict) -> list[str]:
    """Structural defects per the G1 schema (mirrors check_evidence_records.py's
    validate_record). Empty list means the record is valid."""
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
    return defects


def unwrap(data: object) -> list[dict]:
    """A bare list/object is unversioned. An object carrying a `records`
    key is the M5 versioned envelope; unwrap it. Either way, return a
    flat list of record objects."""
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


def evaluate_claim(cid: str, by_claim: dict[str, dict]) -> dict:
    rec = by_claim.get(cid)
    if rec is None:
        return {"claim_id": cid, "status": "missing-record", "evidence_class": None,
                "result": None, "scope": None, "waived": False, "defects": []}
    defects = validate_record(rec)
    if defects:
        return {"claim_id": cid, "status": "invalid",
                "evidence_class": rec.get("evidence_class"),
                "result": rec.get("result"), "scope": rec.get("scope"),
                "waived": False, "defects": defects}
    klass, result, scope = rec["evidence_class"], rec["result"], rec["scope"]
    waived = bool(rec["waiver"])
    if result == "FAIL":
        status = "FAIL"
    elif result == "INCOMPLETE":
        status = "INCOMPLETE"
    elif klass in ASSUMED_CLASSES and not waived:
        status = "unwaived-assumption"
    else:
        status = "PASS"
    return {"claim_id": cid, "status": status, "evidence_class": klass,
            "result": result, "scope": scope, "waived": waived, "defects": []}


def summarize(rows: list[dict]) -> dict:
    status_key = {"PASS": "pass", "FAIL": "fail", "INCOMPLETE": "incomplete",
                  "missing-record": "missing", "invalid": "invalid",
                  "unwaived-assumption": "unwaived_assumption"}
    counts = {v: 0 for v in status_key.values()}
    waived_or_assumed = []
    by_class: dict[str, dict[str, int]] = {}
    for row in rows:
        counts[status_key[row["status"]]] += 1
        if row["waived"]:
            waived_or_assumed.append(row["claim_id"])
        klass = row["evidence_class"]
        if klass is None:
            continue
        bucket = by_class.setdefault(
            klass, {"pass": 0, "fail": 0, "incomplete": 0, "other": 0})
        if row["status"] == "PASS":
            bucket["pass"] += 1
        elif row["status"] == "FAIL":
            bucket["fail"] += 1
        elif row["status"] == "INCOMPLETE":
            bucket["incomplete"] += 1
        else:
            bucket["other"] += 1
    return {
        "total_required": len(rows),
        **counts,
        "waived_or_assumed": sorted(waived_or_assumed),
        "by_evidence_class": by_class,
    }


def compute_verdict(rows: list[dict], by_claim: dict[str, dict],
                     required: list[str]) -> tuple[str, int]:
    if not required:
        return "INCOMPLETE", 3
    if any(r["status"] == "FAIL" for r in rows):
        return "FAILED", 1
    if any(r["status"] in GAP_STATUSES for r in rows):
        return "INCOMPLETE", 3
    profiles = sorted({by_claim[r["claim_id"]]["bindings"]["profile"] for r in rows})
    scope = f"profile={'/'.join(profiles)}"
    waived = sorted(r["claim_id"] for r in rows if r["waived"])
    if waived:
        scope += f"; waived-or-assumed={','.join(waived)}"
    return f"VERIFIED[{scope}]", 0


def build_dashboard(records_path: Path, required: list[str],
                     records: list[dict]) -> tuple[dict, int]:
    by_claim: dict[str, dict] = {}
    for rec in records:
        cid = rec.get("claim_id") if isinstance(rec, dict) else None
        if isinstance(cid, str):
            by_claim[cid] = rec
    rows = [evaluate_claim(cid, by_claim) for cid in required]
    summary = summarize(rows)
    verdict, code = compute_verdict(rows, by_claim, required)
    dashboard = {
        "gate": "coverage-dashboard",
        "records": str(records_path),
        "required_claims": required,
        "rows": rows,
        "summary": summary,
        "verdict": verdict,
    }
    return dashboard, code


def render_text(dashboard: dict) -> str:
    lines = [f"{'CLAIM':<10} {'STATUS':<20} {'CLASS':<20} {'WAIVED':<7} SCOPE"]
    for row in dashboard["rows"]:
        lines.append(
            f"{row['claim_id']:<10} {row['status']:<20} "
            f"{(row['evidence_class'] or '-'):<20} "
            f"{('yes' if row['waived'] else 'no'):<7} "
            f"{row['scope'] or '-'}"
        )
    s = dashboard["summary"]
    lines.append("")
    lines.append(
        f"required={s['total_required']} pass={s['pass']} fail={s['fail']} "
        f"incomplete={s['incomplete']} missing={s['missing']} "
        f"invalid={s['invalid']} unwaived-assumption={s['unwaived_assumption']}"
    )
    if s["waived_or_assumed"]:
        lines.append(f"waived-or-assumed: {', '.join(s['waived_or_assumed'])}")
    lines.append("by evidence_class:")
    for klass, c in sorted(s["by_evidence_class"].items()):
        lines.append(f"  {klass}: pass={c['pass']} fail={c['fail']} "
                      f"incomplete={c['incomplete']} other={c['other']}")
    return "\n".join(lines)


def verdict_line(verdict: str) -> str:
    return f"VERDICT: {verdict}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True, type=Path)
    ap.add_argument("--require", default=None,
                    help="comma-separated claim IDs the profile requires")
    ap.add_argument("--manifest", type=Path, default=None,
                    help="derive required claim IDs from an obligation manifest")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true",
                     help="self-conformance: exit nonzero if this tool's own "
                          "rendered output would ever emit a bare VERIFIED")
    args = ap.parse_args()

    try:
        records = load_records(args.records)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read records: {e}", file=sys.stderr)
        print(verdict_line("ERROR"), file=sys.stderr)
        return 2

    required: list[str] = []
    if args.require:
        required = [c.strip() for c in args.require.split(",") if c.strip()]
    elif args.manifest:
        try:
            manifest = json.loads(args.manifest.read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"ERROR: cannot read manifest: {e}", file=sys.stderr)
            print(verdict_line("ERROR"), file=sys.stderr)
            return 2
        required = [x["id"] for x in manifest.get("invariants", [])] + \
                   [x["id"] for x in manifest.get("witnesses", [])]
    else:
        print("ERROR: pass --require or --manifest — a dashboard with no "
              "required claims covers nothing", file=sys.stderr)
        print(verdict_line("ERROR"), file=sys.stderr)
        return 2

    dashboard, code = build_dashboard(args.records, required, records)

    if args.check:
        text = render_text(dashboard)
        vline = verdict_line(dashboard["verdict"])
        payload = json.dumps(dashboard, indent=2)
        blob = "\n".join([text, vline, payload])
        offending = [ln for ln in blob.splitlines() if UNSCOPED_VERDICT_RE.search(ln)]
        if offending:
            print("CHECK: bare VERIFIED token found in dashboard output:",
                  file=sys.stderr)
            for ln in offending:
                print(f"  {ln}", file=sys.stderr)
            return 1
        print("CHECK: clean, no bare VERIFIED token in dashboard output",
              file=sys.stderr)
        return 0

    if args.json:
        print(json.dumps(dashboard, indent=2))
    else:
        print(render_text(dashboard))
    print(verdict_line(dashboard["verdict"]), file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
