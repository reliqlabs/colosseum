#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
check_ledger_version — validate a ledger envelope's schema version (M5).

The two-gate ledger (C1) consumes G1 evidence records. M5 wraps a record
set in a versioned envelope so a change-loop pass can tell a schema
migration apart from an ordinary source change, and so incremental
re-verification (docs/incremental-reverification.md) can key reuse on the
schema version as well as the per-record source_snapshot bindings.

ENVELOPE

    {
      "ledger_schema_version": "fv-ledger/v2",
      "records": [ <G1 record>, ... ]
    }

A bare JSON list (or a bare single record object) is UNVERSIONED and
treated as v0: still valid input to the gates, but this tool warns, since
an unversioned ledger cannot participate in schema-aware reuse.

This tool checks ONLY the envelope's version field. It does not validate
the records themselves; that is check_evidence_records.py's job (Gate B).

VERDICT (exit code)
    0   recognized version, OR bare/unversioned (with a stderr warning)
    2   an object carrying `ledger_schema_version` whose value is unknown
        or malformed (not a known version string), or unreadable input

USAGE
    check_ledger_version.py --ledger <file.json> [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Versions this toolchain knows how to consume. Add new versions here as the
# ledger schema evolves; an envelope naming a version not in this set is
# rejected so a forward-incompatible ledger fails loudly rather than being
# read under the wrong assumptions.
KNOWN_VERSIONS = {"fv-ledger/v2"}
UNVERSIONED = "unversioned/v0"


def classify(data: object) -> tuple[str, int, str | None]:
    """Return (version, exit_code, warning). warning is None unless the
    ledger is unversioned."""
    # A bare list or a bare single record object is unversioned.
    if isinstance(data, list):
        return UNVERSIONED, 0, "ledger is a bare list (unversioned/v0)"
    if isinstance(data, dict) and "ledger_schema_version" not in data:
        # Could be a bare single record, or an envelope missing its version.
        if "records" in data:
            return (UNVERSIONED, 2,
                    "envelope has a `records` key but no "
                    "`ledger_schema_version`: malformed")
        return UNVERSIONED, 0, "ledger is a bare record object (unversioned/v0)"
    if isinstance(data, dict):
        ver = data.get("ledger_schema_version")
        if not isinstance(ver, str) or not ver.strip():
            return (str(ver), 2,
                    "`ledger_schema_version` is not a non-empty string")
        if ver not in KNOWN_VERSIONS:
            return ver, 2, f"unknown ledger schema version {ver!r}"
        # Recognized version. If it claims to be an envelope it should carry
        # records; warn but do not fail if absent (version check only).
        return ver, 0, None
    return str(type(data).__name__), 2, "ledger is neither a list nor an object"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True, type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        data = json.loads(args.ledger.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read ledger: {e}", file=sys.stderr)
        print("VERDICT: ERROR", file=sys.stderr)
        return 2

    version, code, warning = classify(data)
    record_count = None
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        record_count = len(data["records"])
    elif isinstance(data, list):
        record_count = len(data)

    report = {
        "ledger": str(args.ledger),
        "ledger_schema_version": version,
        "record_count": record_count,
        "known": version in KNOWN_VERSIONS,
        "verdict": "OK" if code == 0 else "REJECTED",
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"version: {version}"
              f"{'' if record_count is None else f'  records: {record_count}'}")

    if warning:
        print(f"WARNING: {warning}", file=sys.stderr)
    print(f"VERDICT: {report['verdict']}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
