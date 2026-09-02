#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
r_ci_selfcheck — infra test for the C10 CI layer (not a Part IV fixture).

Asserts ci.py knows every named check and can run a subset, that
check_doc_links catches a seeded broken file-link and broken anchor in a
temp fixture (and passes clean docs), and that check_dispatch_config
rejects a missing-field config and a duplicate-voice config while
accepting the shipped example.

Exit 0 pass, 1 fail.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CI = REPO / "scripts" / "ci.py"
LINKS = REPO / "scripts" / "check_doc_links.py"
DISPATCH = REPO / "scripts" / "check_dispatch_config.py"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=120)


def main() -> int:
    # --- ci.py knows its checks and validates --only ---
    ci = load(CI, "ci")
    names = {c[0] for c in ci.CHECKS}
    for expected in ("frontmatter", "roster-drift", "doc-links",
                     "dispatch-config", "fixture-tracking", "regression"):
        check(f"ci.py registers check '{expected}'", expected in names)
    check("ci.py: exactly one regression check maps INCOMPLETE",
          sum(1 for c in ci.CHECKS if c[2]) == 1)
    r = run(["uv", "run", "--script", str(CI), "--only", "bogus-check"])
    check("ci.py: unknown --only check is a usage error",
          r.returncode == 2 and "unknown check" in (r.stdout + r.stderr))
    r = run(["uv", "run", "--script", str(CI), "--only", "dispatch-config"])
    check("ci.py: --only runs a single toolchain-free check green",
          r.returncode == 0 and "CI PASSED" in r.stdout, r.stdout[-200:])
    help_run = run(["python3", str(CI), "--help"])
    check("ci.py exposes tolerate-incomplete escape and no legacy strict flag",
          "--tolerate-incomplete" in help_run.stdout and "--strict" not in help_run.stdout)

    # --- check_doc_links catches broken file link + broken anchor ---
    with tempfile.TemporaryDirectory(prefix="cilinks-") as td:
        root = Path(td)
        subprocess.run(["git", "init", "-q"], cwd=root)
        (root / "target.md").write_text("# Real Heading\n\ncontent\n")
        good = root / "good.md"
        good.write_text("# Doc\n\nSee [t](target.md) and [h](target.md#real-heading).\n")
        bad = root / "bad.md"
        bad.write_text(
            "# Doc\n\n[dangling](nope.md) and [anchor](target.md#missing) and "
            "[self](#no-such-section).\n\n"
            "```\n[ignored](alsomissing.md)\n```\n")
        subprocess.run(["git", "add", "-A"], cwd=root)

        r = run(["uv", "run", "--script", str(LINKS), "--root", str(root),
                 "--files", str(good)])
        check("doc-links: clean doc passes", r.returncode == 0, r.stdout[-200:])

        r = run(["uv", "run", "--script", str(LINKS), "--root", str(root),
                 "--files", str(bad)])
        out = r.stdout + r.stderr
        check("doc-links: broken file link caught",
              r.returncode == 1 and "nope.md" in out)
        check("doc-links: broken cross-file anchor caught", "#missing" in out)
        check("doc-links: broken same-file anchor caught", "#no-such-section" in out)
        check("doc-links: link inside fenced code ignored", "alsomissing.md" not in out)

    # --- check_dispatch_config: selftest + direct rejections ---
    r = run(["uv", "run", "--script", str(DISPATCH), "--selftest"])
    check("dispatch-config: selftest passes",
          r.returncode == 0 and "SELFTEST PASSED" in r.stdout, r.stdout[-200:])

    dc = load(DISPATCH, "check_dispatch_config")
    example = json.loads((REPO / "scripts" / "dispatch.config.example.json").read_text())
    check("dispatch-config: example validates", dc.validate(example) == [])
    missing = json.loads(json.dumps(example))
    del missing["omp_native"]["target_spec"]
    check("dispatch-config: missing target_spec rejected",
          any("target_spec" in error for error in dc.validate(missing)))
    duplicate = json.loads(json.dumps(example))
    duplicate["omp_native"]["voices"].append(dict(duplicate["omp_native"]["voices"][0]))
    check("dispatch-config: duplicate voice id rejected",
          any("duplicate voice id" in error for error in dc.validate(duplicate)))
    badslug = json.loads(json.dumps(example))
    badslug["omp_native"]["voices"][0]["id"] = "../evil"
    check("dispatch-config: traversal-shaped voice id rejected",
          any("not a valid slug" in error for error in dc.validate(badslug)))

    print()
    if FAILURES:
        print(f"CI selfcheck: {len(FAILURES)} failure(s)")
        return 1
    print("CI selfcheck: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
