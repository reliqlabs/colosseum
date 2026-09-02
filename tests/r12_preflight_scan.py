#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""R12: OMP fan-out preflight rejects secret material and escaping symlinks."""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FANOUT = REPO / "skills" / "fv-adversarial" / "omp_fanout.py"
FAILURES: list[str] = []


def load_fanout():
    spec = importlib.util.spec_from_file_location("omp_fanout", FANOUT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(label: str, condition: bool, detail: object = "") -> None:
    if condition:
        print(f"  [ok]   {label}")
    else:
        print(f"  [FAIL] {label}" + (f" ({detail})" if detail else ""))
        FAILURES.append(label)


def pem_armor(kind: str) -> str:
    return "-----BEGIN " + kind + "-----\nAAAA\n-----END " + kind + "-----\n"


def main() -> int:
    fanout = load_fanout()
    with tempfile.TemporaryDirectory(prefix="r12-") as temporary:
        root = Path(temporary)
        clean = root / "clean"
        clean.mkdir()
        (clean / "intent.md").write_text("# Intent\n")
        skipped: list[str] = []
        check("clean tree passes", fanout.preflight_scan(clean, skipped) == [])

        secret = root / "secret"
        secret.mkdir()
        (secret / ".env").write_text("FAKE=value\n")
        violations = fanout.preflight_scan(secret)
        check("secret-named file blocks", "secret-named file: .env" in violations, violations)

        key = root / "key"
        key.mkdir()
        (key / "notes.txt").write_text(pem_armor("OPENSSH PRIVATE KEY"))
        violations = fanout.preflight_scan(key)
        check("private-key material blocks", "private-key material: notes.txt" in violations, violations)

        symlink = root / "symlink"
        symlink.mkdir()
        (symlink / "escape").symlink_to("/etc")
        violations = fanout.preflight_scan(symlink)
        check("escaping symlink blocks", any(item.startswith("symlink escapes root: escape") for item in violations), violations)

        derived = root / "derived"
        derived.mkdir()
        cache = derived / "node_modules"
        cache.mkdir()
        (cache / ".env").write_text("ignored derived fixture\n")
        skipped = []
        check("derived directories are skipped explicitly", fanout.preflight_scan(derived, skipped) == [] and skipped == ["node_modules"], skipped)

    print()
    if FAILURES:
        print(f"R12: {len(FAILURES)} failure(s)")
        return 1
    print("R12: all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
