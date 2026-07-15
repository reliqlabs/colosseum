#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
check_fixture_tracking — guard against fixtures the working tree has but git
does not, which ship broken clones (local CI passes, fresh clones fail).

Two failure modes, both caught here:

  1. UNTRACKED: a new fixture file never `git add`ed. `git ls-files --others
     --exclude-standard` finds these.
  2. HIDDEN-IGNORED: a fixture swallowed by a global .gitignore rule — e.g.
     the Rust `target/` build-output rule hiding tests/fixtures/m3b/target,
     or the global `.colosseum/` rule hiding the r22/r28 manifests. The
     untracked scan never lists ignored files, so it misses these. We hit
     this class twice; this check closes it.

An ignored path under tests/fixtures is TOLERATED only if it is a recognized
build/run artifact — regenerated locally, never needed from a clone:
  - a Cargo build dir: a `target/` component whose crate parent holds a
    Cargo.toml (so tests/fixtures/r22/adapter/target stays ignored);
  - a dispatch run artifact: a `.colosseum/verify/` component.
Anything else ignored under tests/fixtures is a broken-clone risk: `git add`
it (negating the ignore in .gitignore), or move it so it is a real build dir.

USAGE  check_fixture_tracking.py [--root DIR] [--selftest]
EXIT   0 clean | 1 a fixture would be missing from a clone | 2 usage/selftest
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

FIXTURES = "tests/fixtures"


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def _lines(root: Path, *args: str) -> list[str]:
    r = git(root, *args)
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def is_build_artifact(root: Path, path: str) -> bool:
    """A regenerable build/run artifact that a clone never needs."""
    parts = path.split("/")
    for i in range(len(parts) - 1):
        if parts[i] == ".colosseum" and parts[i + 1] == "verify":
            return True
    for i, p in enumerate(parts):
        if p == "target":
            crate = "/".join(parts[:i])
            if crate and (root / crate / "Cargo.toml").exists():
                return True
    return False


def find_problems(root: Path) -> list[tuple[str, str]]:
    if not (root / FIXTURES).is_dir():
        return []
    problems: list[tuple[str, str]] = []
    for f in _lines(root, "ls-files", "--others", "--exclude-standard", FIXTURES):
        problems.append(("untracked", f))
    for f in _lines(root, "ls-files", "--others", "--ignored", "--exclude-standard", FIXTURES):
        if not is_build_artifact(root, f):
            problems.append(("hidden-ignored", f))
    return problems


def report(root: Path) -> int:
    problems = find_problems(root)
    if not problems:
        print("fixture-tracking: clean (no fixture would be missing from a clone)")
        return 0
    print("fixture-tracking: fixtures present locally but missing from fresh clones:")
    for kind, f in problems:
        hint = ("git add it" if kind == "untracked"
                else "gitignored; negate the rule and git add it, or make it a real build dir")
        print(f"  [{kind}] {f}  -> {hint}")
    return 1


# ─────────────────────────────────────────────────────────────────────────
def _selftest() -> int:
    fails: list[str] = []

    def expect(label: str, ok: bool) -> None:
        print(f"  [{'ok' if ok else 'FAIL'}] {label}")
        if not ok:
            fails.append(label)

    with tempfile.TemporaryDirectory(prefix="fixtrack-") as td:
        root = Path(td)
        git(root, "init", "-q")
        git(root, "config", "user.email", "t@t")
        git(root, "config", "user.name", "t")
        (root / ".gitignore").write_text("target/\n.colosseum/\n")
        fx = root / FIXTURES
        (fx / "good").mkdir(parents=True)
        (fx / "good" / "data.txt").write_text("x\n")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "base")
        expect("clean tree passes", find_problems(root) == [])

        # untracked, non-ignored fixture
        (fx / "good" / "new.txt").write_text("y\n")
        probs = find_problems(root)
        expect("untracked fixture flagged", ("untracked", f"{FIXTURES}/good/new.txt") in probs)
        (fx / "good" / "new.txt").unlink()

        # ignored non-artifact fixture (target/ with NO Cargo.toml) -> flagged
        (fx / "m3b" / "target").mkdir(parents=True)
        (fx / "m3b" / "target" / "INTENT.md").write_text("i\n")
        probs = find_problems(root)
        expect("hidden-ignored fixture flagged (target, no Cargo.toml)",
               any(k == "hidden-ignored" and "m3b/target/INTENT.md" in f for k, f in probs))

        # real Cargo build dir (target/ WITH Cargo.toml) -> tolerated
        crate = fx / "crate"
        (crate / "target" / "debug").mkdir(parents=True)
        (crate / "Cargo.toml").write_text("[package]\n")
        (crate / "target" / "debug" / "libx.rlib").write_text("bin\n")
        git(root, "add", f"{FIXTURES}/crate/Cargo.toml")
        probs = find_problems(root)
        expect("real Cargo target/ tolerated",
               not any("crate/target" in f for _, f in probs))

        # .colosseum/verify run artifact -> tolerated
        ver = fx / "good" / ".colosseum" / "verify"
        ver.mkdir(parents=True)
        (ver / "run.json").write_text("{}\n")
        probs = find_problems(root)
        expect(".colosseum/verify artifact tolerated",
               not any(".colosseum/verify" in f for _, f in probs))

    print()
    if fails:
        print(f"SELFTEST FAILED: {len(fails)} case(s)")
        return 2
    print("SELFTEST PASSED")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="repo root (default: this repo)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    return report(root)


if __name__ == "__main__":
    sys.exit(main())
