#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R2 + R5 — concurrency and containment (E5).

R5: 24 concurrent `complete` writers, 3 trials, zero lost updates. Before
the manifest lock, interleaved load/save cycles lost 4-7 updates per 24.
Also: empty voice files and stale (pre-run) outputs are refused by
`complete`, and `reset` moves stale output aside.

R2: ledger citations with `../` segments, absolute paths, and symlink
escapes are rejected by containment checks; backtick-quoted paths with
spaces are supported; an unquoted `code:` citation with spaces fails
loudly instead of being silently skipped.

Exit 0 pass, 1 fail.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUN = REPO / "scripts" / "colosseum_run.py"
LEDGER_CHECK = REPO / "scripts" / "check_ledger_references.py"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def crun(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["uv", "run", "--script", str(RUN), *args],
                          capture_output=True, text=True, timeout=300)


def r5_trial(tmp: Path, trial: int) -> int:
    """Returns the number of voices left NOT complete after 24 concurrent writers."""
    n = 24
    voices = [f"v{i:02d}" for i in range(n)]
    run_dir = tmp / f"trial{trial}"
    target = tmp / "intent.md"
    r = crun("init", str(target), f"--voices={','.join(voices)}",
             "--owners=" + ",".join(f"{v}:opencode" for v in voices),
             f"--run-dir={run_dir}")
    if r.returncode != 0:
        raise RuntimeError(f"init failed: {r.stderr}")
    manifest = json.loads((run_dir / "run.json").read_text())
    for v in manifest["voices"]:
        (run_dir / v["file"]).write_text(f"## Attacks\n\nreport for {v['id']}\n")

    def complete(voice: str) -> int:
        return crun("complete", str(run_dir), f"--voice={voice}",
                    "--elapsed=1", "--finish-reason=stop").returncode

    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        codes = list(pool.map(complete, voices))
    if any(c != 0 for c in codes):
        return sum(1 for c in codes if c != 0)
    manifest = json.loads((run_dir / "run.json").read_text())
    return sum(1 for v in manifest["voices"] if v["status"] != "complete")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="r5-") as td:
        tmp = Path(td)
        (tmp / "intent.md").write_text("# intent\n")

        for trial in range(1, 4):
            lost = r5_trial(tmp, trial)
            check(f"R5 trial {trial}: 24 concurrent complete writers, zero lost updates",
                  lost == 0, f"{lost} lost/failed")

        # complete refuses empty and stale outputs; reset moves output aside.
        run_dir = tmp / "guards"
        crun("init", str(tmp / "intent.md"), "--voices=g1",
             "--owners=g1:opencode", f"--run-dir={run_dir}")
        manifest = json.loads((run_dir / "run.json").read_text())
        vfile = run_dir / manifest["voices"][0]["file"]

        vfile.write_text("")
        r = crun("complete", str(run_dir), "--voice=g1")
        check("R5: empty voice file refused by complete",
              r.returncode != 0 and "empty" in (r.stdout + r.stderr))

        vfile.write_text("real report\n")
        old = time.time() - 86400
        os.utime(vfile, (old, old))
        r = crun("complete", str(run_dir), "--voice=g1")
        check("R5: stale (pre-run) output refused by complete",
              r.returncode != 0 and "stale" in (r.stdout + r.stderr))

        os.utime(vfile, None)
        r = crun("complete", str(run_dir), "--voice=g1")
        check("R5: fresh non-empty output accepted", r.returncode == 0,
              (r.stdout + r.stderr)[-200:])
        crun("reset", str(run_dir), "--voice=g1")
        check("R5: reset moves stale output aside",
              not vfile.exists() and (run_dir / f"{vfile.name}.attempt1").exists())

    # ── R2: citation containment ───────────────────────────────────────
    with tempfile.TemporaryDirectory(prefix="r2-") as td:
        tmp = Path(td)
        root = tmp / "proj"
        (root / ".colosseum").mkdir(parents=True)
        (root / "src").mkdir()
        (root / "src" / "lib.rs").write_text("fn main() {}\nlet x = 1;\n")
        (root / "src" / "my file.rs").write_text("fn spaced() {}\n")
        outside = tmp / "outside.rs"
        outside.write_text("secret code\n")
        (root / "src" / "link.rs").symlink_to(outside)

        def gate(ledger_text: str) -> tuple[int, str]:
            ledger = root / ".colosseum" / "ledger.md"
            ledger.write_text(ledger_text)
            proc = subprocess.run(
                [sys.executable, str(LEDGER_CHECK), str(ledger), "--root", str(root)],
                capture_output=True, text=True, timeout=60)
            return proc.returncode, proc.stdout + proc.stderr

        code, out = gate("- L1 enforced at `src/lib.rs:2`. kani: skipped because fixture.\n")
        check("R2: clean citation passes", code == 0, out[-200:])

        code, out = gate("- L1 at `../outside.rs:1`. kani: skipped because fixture.\n")
        check("R2: `../` citation rejected",
              code == 1 and "escapes the canonical root" in out)

        code, out = gate(f"- L1 at `{outside}:1`. kani: skipped because fixture.\n")
        check("R2: absolute-path citation rejected",
              code == 1 and "escapes the canonical root" in out)

        code, out = gate("- L1 at `src/link.rs:1`. kani: skipped because fixture.\n")
        check("R2: symlink-escape citation rejected",
              code == 1 and "symlink escape" in out)

        code, out = gate("- L1 at `src/my file.rs:1`. kani: skipped because fixture.\n")
        check("R2: backtick-quoted space path supported", code == 0, out[-200:])

        code, out = gate("- L1 code: src/my file.rs:1 . kani: skipped because fixture.\n")
        check("R2: unquoted space path in code: fails loudly",
              code == 1 and "unparseable" in out)

    print()
    if FAILURES:
        print(f"R2/R5: {len(FAILURES)} failure(s)")
        return 1
    print("R2/R5: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
