#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
check_doc_links — internal link and anchor checker for repo docs (C10).

Offline. Scans tracked Markdown for links that must resolve inside the
repo and fails CI when one dangles:

  file links     [text](path) and bare `path.md` refs must point at an
                 existing file, resolved relative to the linking doc (and,
                 for root-absolute `/path`, the repo root)
  anchors        [text](#slug) and [text](other.md#slug) must match a
                 GitHub-style heading slug in the target file

External http(s)/mailto links are listed but never fetched. Fenced and
inline code is stripped first so snippets do not raise false positives,
and angle-bracket placeholders (`<your-clone-url>`, `<pinned-release>`)
are ignored.

USAGE
    check_doc_links.py [--root <repo>] [--files a.md b.md ...] [--list-external]

EXIT
    0 all internal links and anchors resolve
    1 one or more broken internal links/anchors
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

FENCE_RE = re.compile(r"^```")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
# [text](target) — target up to the first whitespace or closing paren.
LINK_RE = re.compile(r"\[(?:[^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:")


def strip_code(text: str) -> str:
    """Blank out fenced blocks and inline code so links inside samples are
    not checked. Fenced blocks are replaced line-for-line to keep numbers."""
    out = []
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else INLINE_CODE_RE.sub("", line))
    return "\n".join(out)


def slugify(heading: str) -> str:
    """GitHub heading-slug approximation: lowercase, strip formatting and
    punctuation except hyphens, spaces to hyphens."""
    text = re.sub(r"`[^`]*`", lambda m: m.group(0).strip("`"), heading)
    text = re.sub(r"[*_~]", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # link text only
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text


def heading_slugs(path: Path) -> set[str]:
    slugs: dict[str, int] = {}
    result: set[str] = set()
    try:
        body = strip_code(path.read_text(errors="replace"))
    except OSError:
        return result
    for line in body.splitlines():
        m = HEADING_RE.match(line)
        if not m:
            continue
        base = slugify(m.group(2))
        n = slugs.get(base, 0)
        slugs[base] = n + 1
        result.add(base if n == 0 else f"{base}-{n}")
    return result


def is_placeholder(target: str) -> bool:
    return "<" in target or ">" in target or target.startswith("{")


# Live docs only. `scratchpad/` is throwaway; `archive/` is a frozen
# one-time snapshot of historical transcripts/memory (see .gitignore) whose
# internal links reflect its captured state — rewriting them would falsify
# the snapshot, so the gate does not police it.
EXCLUDED_DIRS = ("scratchpad/", "archive/")


def tracked_md(root: Path) -> list[Path]:
    out = subprocess.run(["git", "-C", str(root), "ls-files", "*.md"],
                         capture_output=True, text=True)
    files = [root / line for line in out.stdout.splitlines() if line.strip()]
    return [f for f in files if f.is_file()
            and not any(ex in str(f.relative_to(root)) for ex in EXCLUDED_DIRS)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--files", nargs="*", type=Path, default=None)
    ap.add_argument("--list-external", action="store_true")
    args = ap.parse_args()
    root = args.root.resolve()

    docs = [f.resolve() for f in args.files] if args.files else tracked_md(root)
    broken: list[str] = []
    external: list[str] = []
    slug_cache: dict[Path, set[str]] = {}

    def slugs_for(p: Path) -> set[str]:
        if p not in slug_cache:
            slug_cache[p] = heading_slugs(p)
        return slug_cache[p]

    for doc in docs:
        body = strip_code(doc.read_text(errors="replace"))
        rel = doc.relative_to(root) if doc.is_relative_to(root) else doc
        for lineno, line in enumerate(body.splitlines(), 1):
            for target in LINK_RE.findall(line):
                if target.startswith(EXTERNAL_PREFIXES):
                    external.append(f"{rel}:{lineno}: {target}")
                    continue
                if is_placeholder(target):
                    continue
                path_part, _, anchor = target.partition("#")
                if not path_part:  # same-file anchor
                    if anchor and slugify(anchor) not in slugs_for(doc):
                        broken.append(f"{rel}:{lineno}: missing anchor #{anchor}")
                    continue
                base = root if path_part.startswith("/") else doc.parent
                dest = (base / path_part.lstrip("/")).resolve()
                if not dest.exists():
                    broken.append(f"{rel}:{lineno}: dangling link -> {path_part}")
                    continue
                if anchor and dest.suffix == ".md":
                    if slugify(anchor) not in slugs_for(dest):
                        broken.append(f"{rel}:{lineno}: {path_part} missing anchor #{anchor}")

    if args.list_external:
        for e in external:
            print(f"  [external] {e}")

    print(f"checked {len(docs)} doc(s); {len(external)} external link(s) not fetched")
    for b in broken:
        print(f"FAIL: {b}", file=sys.stderr)
    if broken:
        print(f"\nLINK CHECK FAILED: {len(broken)} broken internal link(s)/anchor(s)",
              file=sys.stderr)
        return 1
    print("LINK CHECK PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
