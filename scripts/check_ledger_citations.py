#!/usr/bin/env python3
"""
check_ledger_citations.py — the ledger-as-gate CI check.

Reference implementation for Step 8 of skills/colosseum-compose/SKILL.md.
Copy to <project>/.colosseum/scripts/ and invoke from CI on every revision.

Four checks, per the SKILL:

1. Citation resolution — every `<file>:<line>` citation in the ledger
   (either backtick-quoted, e.g. `specs/RcvSpec.lean:263`, or an explicit
   `code: <file>:<line>` annotation) must point at an existing file and a
   line number within that file.
2. Citation content sanity — the cited line must be non-empty and not a
   comment-only line. A citation pointing at `// TODO` is the same shape
   of drift as a missing citation.
3. Kani coverage — every trust-chain link should carry either a `kani:`
   harness reference or a `kani: skipped because <reason>` annotation.
   Detecting "trust-chain link" generically across ledger layouts is
   unreliable, so this check WARNS by default and fails only under
   --strict-kani (use once your ledger's kani annotations are complete).
4. Axiom annotation — every `axiom:` annotation must be followed by a
   justification phrase, not bare.

USAGE
    check_ledger_citations.py <ledger.md> [--root <project-root>] [--strict-kani]

    --root defaults to the ledger's grandparent directory (i.e. the
    project root when the ledger lives at <project>/.colosseum/ledger.md).

EXIT CODES
    0 — all checks passed
    1 — at least one gate failure
    2 — usage / IO error
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# `path:line` citations: backtick-quoted or after a `code:` annotation.
# Path must contain a dot-extension to avoid matching prose ratios ("5:1").
CITATION_RE = re.compile(
    r"`(?P<path>[A-Za-z0-9_./\-]+\.[A-Za-z0-9]+):(?P<line>\d+)`"
    r"|code:\s*(?P<path2>[A-Za-z0-9_./\-]+\.[A-Za-z0-9]+):(?P<line2>\d+)"
)
# Bare `axiom:` with nothing meaningful after it on the same line.
AXIOM_RE = re.compile(r"axiom:\s*(?P<just>.*)$")
KANI_RE = re.compile(r"kani:\s*(?P<body>.*)$")

COMMENT_PREFIXES = ("//", "#", "--", "/*", "*", ";")


def is_comment_only(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    return any(stripped.startswith(p) for p in COMMENT_PREFIXES)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ledger", help="path to ledger.md")
    ap.add_argument("--root", default=None, help="project root that citations resolve against")
    ap.add_argument("--strict-kani", action="store_true", help="fail (not warn) on missing kani annotations")
    args = ap.parse_args()

    ledger_path = Path(args.ledger).resolve()
    if not ledger_path.exists():
        print(f"FATAL: ledger not found at {ledger_path}", file=sys.stderr)
        return 2

    root = Path(args.root).resolve() if args.root else ledger_path.parent.parent
    ledger_lines = ledger_path.read_text().splitlines()

    failures: list[str] = []
    warnings: list[str] = []
    n_citations = 0
    n_axioms = 0
    n_kani = 0

    file_cache: dict[Path, list[str]] = {}

    def load(p: Path) -> list[str] | None:
        if p not in file_cache:
            try:
                file_cache[p] = p.read_text(errors="replace").splitlines()
            except OSError:
                file_cache[p] = None  # type: ignore[assignment]
        return file_cache[p]

    for lineno, text in enumerate(ledger_lines, start=1):
        for m in CITATION_RE.finditer(text):
            rel = m.group("path") or m.group("path2")
            cited_line = int(m.group("line") or m.group("line2"))
            n_citations += 1
            target = (root / rel).resolve()
            contents = load(target)
            if contents is None:
                failures.append(
                    f"ledger:{lineno}: citation `{rel}:{cited_line}` — file not found under {root}"
                )
                continue
            if cited_line < 1 or cited_line > len(contents):
                failures.append(
                    f"ledger:{lineno}: citation `{rel}:{cited_line}` — line out of range (file has {len(contents)} lines)"
                )
                continue
            cited = contents[cited_line - 1]
            if is_comment_only(cited):
                failures.append(
                    f"ledger:{lineno}: citation `{rel}:{cited_line}` — cited line is empty or comment-only: {cited.strip()!r}"
                )

        am = AXIOM_RE.search(text)
        if am:
            n_axioms += 1
            just = am.group("just").strip().rstrip("*_`")
            if len(just) < 8:
                failures.append(
                    f"ledger:{lineno}: bare `axiom:` annotation with no justification phrase"
                )

        km = KANI_RE.search(text)
        if km:
            n_kani += 1
            body = km.group("body").strip()
            if body.startswith("skipped") and "because" not in body:
                msg = f"ledger:{lineno}: `kani: skipped` without a `because <reason>` clause"
                (failures if args.strict_kani else warnings).append(msg)

    if n_kani == 0:
        msg = "ledger contains no `kani:` annotations — trust-chain links lack harness coverage or explicit skips"
        (failures if args.strict_kani else warnings).append(msg)

    print(f"Citations checked: {n_citations}")
    print(f"Axiom annotations: {n_axioms}")
    print(f"Kani annotations:  {n_kani}")
    for w in warnings:
        print(f"WARN: {w}")
    for f in failures:
        print(f"FAIL: {f}")
    if failures:
        print(f"\nGATE FAILED: {len(failures)} failure(s)")
        return 1
    print("\nGATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
