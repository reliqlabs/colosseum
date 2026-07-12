#!/usr/bin/env python3
"""
check_ledger_references.py — the REFERENCE-INTEGRITY gate (Gate A of the
two-gate ledger split, C1).

This gate checks that the ledger's references hook into the live codebase:
paths resolve inside the canonical root, cited lines exist and carry real
content, annotations are well-formed. It does NOT judge whether the cited
evidence semantically discharges any claim — that is the semantic evidence
gate (`check_evidence_records.py`, Gate B), which validates claim-ID-keyed
G1 records. A ledger can pass this gate and still describe an unverified
system; passing here means only that nothing it points at has drifted.

Reference implementation for Step 8 of skills/colosseum-compose/SKILL.md.
Copy to <project>/.colosseum/scripts/ and invoke from CI on every revision.

Checks:

1. Citation resolution — every `<file>:<line>` citation in the ledger
   (either backtick-quoted, e.g. `specs/RcvSpec.lean:263`, or an explicit
   `code: <file>:<line>` annotation) must point at an existing file and a
   line number within that file, contained inside the canonical root.
2. Citation content sanity — the cited line must be non-empty and not a
   comment-only line (Rust `#[...]` attribute lines are valid targets).
   A citation pointing at `// TODO` is the same shape of drift as a
   missing citation.
3. Content-hash binding — a citation may bind the cited line's content
   with an `@sha256:<12hex>` suffix (first 12 hex chars of the SHA-256 of
   the line with trailing whitespace stripped). When present, a changed
   line — moved symbol, inserted lines above, enforcement stubbed out —
   fails the gate instead of silently pointing at the wrong code. Use
   --suggest-hashes to print the binding suffix for every unhashed
   citation.
4. No vacuous pass — an empty ledger, or one containing zero citations,
   FAILS. A gate with nothing to check has checked nothing.
5. Kani coverage — every trust-chain link (a `Depends on:` entry line)
   should carry either a `kani:` harness reference or a
   `kani: skipped because <reason>` annotation. Per-link misses WARN by
   default and fail under --strict-kani (use once your ledger's kani
   annotations are complete). Zero `kani:` annotations in the whole
   ledger follows the same strictness switch.
6. Axiom annotation — every `axiom:` occurrence (each one on a line, not
   just the first) must carry a meaningful justification phrase: at
   least three words, not a placeholder (TODO/tbd/n/a/...).

USAGE
    check_ledger_references.py <ledger.md> [--root <project-root>]
        [--strict-kani] [--suggest-hashes]

    --root defaults to the ledger's grandparent directory (i.e. the
    project root when the ledger lives at <project>/.colosseum/ledger.md).

EXIT CODES
    0 — all checks passed
    1 — at least one gate failure
    2 — usage / IO error
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

# `path:line` citations: backtick-quoted or after a `code:` annotation,
# optionally content-bound with an `@sha256:<12hex>` suffix.
# Path must contain a dot-extension to avoid matching prose ratios ("5:1").
# Backtick-quoted paths may contain spaces (the backticks delimit them);
# bare `code:` paths cannot, and a space-path there fails loudly below.
CITATION_RE = re.compile(
    r"`(?P<path>[^`\n]+?\.[A-Za-z0-9]+):(?P<line>\d+)(?:@sha256:(?P<hash>[0-9a-f]{12}))?`"
    r"|code:\s*(?P<path2>[^\s`]+\.[A-Za-z0-9]+):(?P<line2>\d+)(?:@sha256:(?P<hash2>[0-9a-f]{12}))?"
)
# A `code:` annotation whose value looks like a citation but did not parse
# (spaces in an unquoted path, stray characters): fail loudly instead of
# silently skipping the check.
UNPARSED_CODE_RE = re.compile(r"code:\s*(?P<rest>[^\n]*\.[A-Za-z0-9]+:\d+)")
KANI_RE = re.compile(r"kani:\s*(?P<body>.*)$")
DEPENDS_HEADER_RE = re.compile(r"^\s*Depends on:\s*$")
LINK_LINE_RE = re.compile(r"^\s*-\s+\S")

COMMENT_PREFIXES = ("//", "#", "--", "/*", "*", ";")

# Justifications that name no reason. First-word placeholders fail the
# meaningful-justification threshold regardless of length.
PLACEHOLDER_WORDS = {"todo", "tbd", "n/a", "na", "fixme", "xxx", "later", "pending", "???"}


def is_comment_only(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("#["):
        return False  # Rust attribute lines (`#[kani::proof]`) are valid targets
    return any(stripped.startswith(p) for p in COMMENT_PREFIXES)


def line_hash(line: str) -> str:
    """Content binding for a cited line: SHA-256 of the line with trailing
    whitespace stripped, truncated to 12 hex chars (hand-writable)."""
    return hashlib.sha256(line.rstrip().encode()).hexdigest()[:12]


def meaningful_justification(just: str) -> bool:
    just = just.strip().strip("*_`").strip()
    words = re.findall(r"[A-Za-z][A-Za-z\-']*", just)
    if len(words) < 3:
        return False
    return words[0].lower() not in PLACEHOLDER_WORDS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ledger", help="path to ledger.md")
    ap.add_argument("--root", default=None, help="project root that citations resolve against")
    ap.add_argument("--strict-kani", action="store_true", help="fail (not warn) on missing kani annotations")
    ap.add_argument("--suggest-hashes", action="store_true",
                    help="print the @sha256 binding suffix for every citation that lacks one")
    args = ap.parse_args()

    ledger_path = Path(args.ledger).resolve()
    if not ledger_path.exists():
        print(f"FATAL: ledger not found at {ledger_path}", file=sys.stderr)
        return 2

    root = Path(args.root).resolve() if args.root else ledger_path.parent.parent
    ledger_lines = ledger_path.read_text().splitlines()

    failures: list[str] = []
    warnings: list[str] = []
    suggestions: list[str] = []
    n_citations = 0
    n_hashed = 0
    n_axioms = 0
    n_kani = 0
    n_links = 0
    in_depends_block = False

    file_cache: dict[Path, list[str]] = {}

    def load(p: Path) -> list[str] | None:
        if p not in file_cache:
            try:
                file_cache[p] = p.read_text(errors="replace").splitlines()
            except OSError:
                file_cache[p] = None  # type: ignore[assignment]
        return file_cache[p]

    for lineno, text in enumerate(ledger_lines, start=1):
        matched_spans: list[tuple[int, int]] = []
        for m in CITATION_RE.finditer(text):
            matched_spans.append(m.span())
            rel = m.group("path") or m.group("path2")
            cited_line = int(m.group("line") or m.group("line2"))
            bound_hash = m.group("hash") or m.group("hash2")
            n_citations += 1
            # Containment: citations resolve inside the canonical root only.
            # `..` segments are rejected textually; resolve() then also
            # catches absolute paths and symlink escapes.
            if ".." in Path(rel).parts or Path(rel).is_absolute():
                failures.append(
                    f"ledger:{lineno}: citation `{rel}:{cited_line}` — path escapes the "
                    f"canonical root (`..` or absolute path)"
                )
                continue
            target = (root / rel).resolve()
            if not target.is_relative_to(root):
                failures.append(
                    f"ledger:{lineno}: citation `{rel}:{cited_line}` — resolves outside "
                    f"the canonical root ({target}); symlink escape?"
                )
                continue
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
                continue
            if bound_hash:
                n_hashed += 1
                actual = line_hash(cited)
                if actual != bound_hash:
                    failures.append(
                        f"ledger:{lineno}: citation `{rel}:{cited_line}` — content hash mismatch "
                        f"(bound @sha256:{bound_hash}, line now hashes @sha256:{actual}): the cited "
                        f"line changed — moved symbol, inserted lines, or stubbed enforcement"
                    )
            elif args.suggest_hashes:
                suggestions.append(f"{rel}:{cited_line}@sha256:{line_hash(cited)}")

        for um in UNPARSED_CODE_RE.finditer(text):
            overlaps = any(s <= um.start() < e or s < um.end() <= e
                           for s, e in matched_spans)
            if not overlaps:
                failures.append(
                    f"ledger:{lineno}: unparseable `code:` citation "
                    f"{um.group('rest')!r} — spaces in an unquoted path? "
                    f"Quote the whole path:line in backticks."
                )

        # Every `axiom:` occurrence on the line is checked, not just the
        # first; each is anchored to its own justification segment.
        if "axiom:" in text:
            segments = text.split("axiom:")[1:]
            for seg in segments:
                n_axioms += 1
                just = seg.split("axiom:")[0]
                # a following annotation on the same line ends the phrase
                just = re.split(r"\b(?:code|kani):", just)[0]
                if not meaningful_justification(just):
                    failures.append(
                        f"ledger:{lineno}: `axiom:` annotation without a meaningful "
                        f"justification phrase (got {just.strip()!r}; need at least "
                        f"three words, no placeholder)"
                    )

        km = KANI_RE.search(text)
        if km:
            n_kani += 1
            body = km.group("body").strip()
            if body.startswith("skipped") and "because" not in body:
                msg = f"ledger:{lineno}: `kani: skipped` without a `because <reason>` clause"
                (failures if args.strict_kani else warnings).append(msg)

        # Per-link Kani coverage: every entry line of a `Depends on:` block
        # is a trust-chain link and must carry `kani:` (harness or explicit
        # skip). Warn by default; gate under --strict-kani.
        if DEPENDS_HEADER_RE.match(text):
            in_depends_block = True
        elif in_depends_block:
            if LINK_LINE_RE.match(text):
                n_links += 1
                if "kani:" not in text:
                    msg = (f"ledger:{lineno}: trust-chain link without `kani:` harness "
                           f"reference or explicit skip: {text.strip()[:80]!r}")
                    (failures if args.strict_kani else warnings).append(msg)
            elif text.strip():
                in_depends_block = False

    # No vacuous pass: a ledger with nothing to check has checked nothing.
    if n_citations == 0:
        failures.append(
            "ledger contains no code citations — empty or prose-only ledgers FAIL, "
            "they do not vacuously pass"
        )

    if n_kani == 0:
        msg = "ledger contains no `kani:` annotations — trust-chain links lack harness coverage or explicit skips"
        (failures if args.strict_kani else warnings).append(msg)

    print(f"Citations checked: {n_citations} ({n_hashed} content-bound)")
    print(f"Axiom annotations: {n_axioms}")
    print(f"Kani annotations:  {n_kani}")
    print(f"Trust-chain links: {n_links}")
    for w in warnings:
        print(f"WARN: {w}")
    for f in failures:
        print(f"FAIL: {f}")
    if suggestions:
        print("\nContent-hash suggestions (append to the citation):")
        for s in suggestions:
            print(f"  {s}")
    if failures:
        print(f"\nGATE FAILED: {len(failures)} failure(s)")
        return 1
    print("\nGATE PASSED (reference integrity only — semantic evidence is "
          "check_evidence_records.py's gate)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
