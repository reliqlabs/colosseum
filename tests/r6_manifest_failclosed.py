#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R6 — manifest fail-closed control flow in colosseum_run.py (E4, contract G2).

Zero-voice manifests are invalid runs everywhere they could be read;
duplicate voice ids are rejected at init and at load; an all-errored
`wait` exits nonzero (all-terminal is not success when zero voices
completed); `synthesize` refuses pending/errored inputs without an
explicit --allow-partial and labels the output PARTIAL when overridden;
zero completed voices cannot be synthesized at all; `reset` retains the
prior attempt in the voice's history instead of erasing it.

Exit 0 pass, 1 fail.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUN = REPO / "scripts" / "colosseum_run.py"
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
                          capture_output=True, text=True, timeout=120)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="r6-") as td:
        tmp = Path(td)
        target = tmp / "intent.md"
        target.write_text("# intent\n")

        r = crun("init", str(target), "--voices=", "--owners=")
        check("init: empty --voices rejected",
              r.returncode != 0 and "zero-voice" in (r.stdout + r.stderr))

        r = crun("init", str(target), "--voices=a,a", "--owners=a:opencode")
        check("init: duplicate voice ids rejected",
              r.returncode != 0 and "duplicate" in (r.stdout + r.stderr))

        # Hand-built zero-voice manifest: every reader must refuse it.
        zero_dir = tmp / "zero"
        zero_dir.mkdir()
        (zero_dir / "run.json").write_text(json.dumps(
            {"run_id": "z", "target": str(target), "created": "t", "voices": [],
             "synthesis": {"file": "synthesis.md", "harness": "x", "status": "pending"}}))
        for sub in (["status", str(zero_dir)],
                    ["wait", str(zero_dir), "--timeout=3"],
                    ["synthesize", str(zero_dir)]):
            r = crun(*sub)
            check(f"zero-voice manifest refused by `{sub[0]}`",
                  r.returncode != 0 and "zero voices" in (r.stdout + r.stderr),
                  f"exit={r.returncode}")

        # Real run: two voices.
        run_dir = tmp / "run"
        r = crun("init", str(target), "--voices=v1,v2",
                 "--owners=v1:opencode,v2:opencode", f"--run-dir={run_dir}")
        check("init: two-voice run created", r.returncode == 0, r.stderr[-200:])

        # All-errored wait -> nonzero (zero evidence).
        crun("error", str(run_dir), "--voice=v1", "--detail=HTTP 500", "--elapsed=1")
        crun("error", str(run_dir), "--voice=v2", "--detail=timeout", "--elapsed=2")
        r = crun("wait", str(run_dir), "--timeout=3")
        check("wait: all-errored run exits nonzero with INCOMPLETE",
              r.returncode == 2 and "INCOMPLETE" in (r.stdout + r.stderr),
              f"exit={r.returncode}")

        # Zero completed voices: synthesize refuses even with override.
        r = crun("synthesize", str(run_dir), "--allow-partial")
        check("synthesize: zero completed voices refused even with --allow-partial",
              r.returncode != 0 and "zero completed" in (r.stdout + r.stderr))

        # Reset v1, complete it; history must retain the errored attempt.
        crun("reset", str(run_dir), "--voice=v1")
        manifest = json.loads((run_dir / "run.json").read_text())
        v1 = next(v for v in manifest["voices"] if v["id"] == "v1")
        check("reset: prior errored attempt retained in history",
              len(v1.get("history", [])) == 1
              and v1["history"][0]["status"] == "error"
              and v1["history"][0]["error_detail"] == "HTTP 500")

        (run_dir / v1["file"]).write_text("## Attacks\n\nVERDICT: BREAKS\n")
        crun("complete", str(run_dir), "--voice=v1", "--elapsed=3",
             "--finish-reason=stop")

        # One complete + one errored: refused without override, labeled with.
        r = crun("synthesize", str(run_dir))
        check("synthesize: errored voice refused without --allow-partial",
              r.returncode != 0 and "--allow-partial" in (r.stdout + r.stderr))
        r = crun("synthesize", str(run_dir), "--allow-partial")
        synth = (run_dir / "synthesis-input.md").read_text() \
            if (run_dir / "synthesis-input.md").exists() else ""
        check("synthesize: --allow-partial produces PARTIAL-labeled output",
              r.returncode == 0 and "PARTIAL SYNTHESIS INPUT" in synth
              and "coverage gap" in synth,
              f"exit={r.returncode}")

        # Mixed-terminal wait: one complete + one errored is exit 0 (evidence exists).
        r = crun("wait", str(run_dir), "--timeout=3")
        check("wait: terminal run with at least one completion exits 0",
              r.returncode == 0, f"exit={r.returncode}")

    print()
    if FAILURES:
        print(f"R6: {len(FAILURES)} failure(s)")
        return 1
    print("R6: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
