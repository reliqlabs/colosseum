#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R3 + R4 + R15 — dispatch fail-closed control flow (E4, contracts G1/G2).

R3: dispatch with the `opencode` binary absent exits nonzero and says
INCOMPLETE — a missing tool is never a quiet no-op.
R4: unknown --voices/--slices filters are errors, not 0-call successes;
duplicate voice/slice names and traversal-shaped ids are rejected; a
missing target_spec is fatal.
R15: the versioned event parser extracts the final assistant message from
a --format json stream (finish_reason + token usage captured), tolerates
truncated and malformed lines, surfaces error events, falls back to
plaintext for non-event output, and hands downstream consumers (the stub
detector) only extracted text, never JSON.

Exit 0 pass, 1 fail.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DISPATCH = REPO / "scripts" / "opencode_dispatch.py"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def load_dispatch_module():
    spec = importlib.util.spec_from_file_location("opencode_dispatch", DISPATCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_project(root: Path) -> Path:
    proj = root / "proj"
    proj.mkdir(parents=True)
    (proj / "intent.md").write_text("# Intent\n\n## 1. Scope\n\nfixture\n")
    for cmd in (["git", "init", "-q"],
                ["git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A"],
                ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "f"]):
        subprocess.run(cmd, cwd=proj, capture_output=True)
    return proj


def write_config(proj: Path, **overrides) -> Path:
    cfg = {
        "project_root": str(proj),
        "target_spec": str(proj / "intent.md"),
        "run_tag_prefix": "r3",
        "voices": [{"id": "dummy", "model": "none/none"}],
        "slices": [{"name": "s", "label": "s", "headers": ["## 1."], "attack_emphasis": "n/a"}],
        "per_call_timeout": 5,
        "max_retries": 0,
    }
    cfg.update(overrides)
    path = proj / "dispatch.json"
    path.write_text(json.dumps(cfg))
    return path


def dispatch(cfg_path: Path, *extra: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "--script", str(DISPATCH), "--config", str(cfg_path), *extra],
        capture_output=True, text=True, env=env, timeout=300,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="r3r4-") as td:
        tmp = Path(td)

        # ── R3: opencode binary absent ─────────────────────────────────
        proj = make_project(tmp / "r3")
        cfg = write_config(proj)
        bin_dir = tmp / "thinbin"
        bin_dir.mkdir()
        for tool in ("uv", "git", "python3"):
            src = shutil.which(tool)
            if src:
                (bin_dir / tool).symlink_to(src)
        thin_env = {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin"}
        r = dispatch(cfg, env=thin_env)
        out = r.stdout + r.stderr
        check("R3: opencode absent -> nonzero exit", r.returncode != 0,
              f"exit={r.returncode}")
        check("R3: verdict INCOMPLETE stated", "INCOMPLETE" in out)
        check("R3: violation names the missing binary", "opencode binary not found" in out)

        # ── R4: selection and config validation ───────────────────────
        proj = make_project(tmp / "r4")
        cfg = write_config(proj)
        r = dispatch(cfg, "--voices=nope")
        check("R4: unknown --voices is an error, not a 0-call success",
              r.returncode != 0 and "not in config" in (r.stdout + r.stderr),
              f"exit={r.returncode}")
        r = dispatch(cfg, "--slices=ghost")
        check("R4: unknown --slices is an error",
              r.returncode != 0 and "not in config" in (r.stdout + r.stderr))

        dup = write_config(proj, voices=[{"id": "a", "model": "x/y"},
                                         {"id": "a", "model": "x/z"}])
        r = dispatch(dup)
        check("R4: duplicate voice ids rejected",
              r.returncode != 0 and "duplicate" in (r.stdout + r.stderr))

        dupslice = write_config(proj, slices=[
            {"name": "s", "label": "1", "headers": [], "attack_emphasis": ""},
            {"name": "s", "label": "2", "headers": [], "attack_emphasis": ""}])
        r = dispatch(dupslice)
        check("R4: duplicate slice names rejected",
              r.returncode != 0 and "duplicate" in (r.stdout + r.stderr))

        evil = write_config(proj, voices=[{"id": "../escape", "model": "x/y"}])
        r = dispatch(evil)
        check("R4: traversal-shaped voice id rejected",
              r.returncode != 0 and "invalid voice id" in (r.stdout + r.stderr))

        gone = write_config(proj, target_spec=str(proj / "missing.md"))
        r = dispatch(gone)
        check("R4: missing target_spec is fatal",
              r.returncode != 0 and "target_spec does not exist" in (r.stdout + r.stderr))

        zero = write_config(proj, voices=[])
        r = dispatch(zero)
        check("R4: zero-voice config is an invalid run",
              r.returncode != 0 and "zero voices" in (r.stdout + r.stderr))

    # ── R15: event parser ──────────────────────────────────────────────
    mod = load_dispatch_module()
    parse = mod.parse_event_stream

    report_text = "## Attacks\n\n### 1. Finding\n" + "x" * 600 + "\nVERDICT: BREAKS"
    good = "\n".join([
        json.dumps({"type": "step_start", "timestamp": 1, "sessionID": "s",
                    "part": {"id": "p0", "type": "step-start"}}),
        json.dumps({"type": "text", "timestamp": 2, "sessionID": "s",
                    "part": {"id": "p1", "type": "text", "text": report_text}}),
        json.dumps({"type": "step_finish", "timestamp": 3, "sessionID": "s",
                    "part": {"id": "p2", "type": "step-finish", "reason": "stop",
                             "tokens": {"input": 100, "output": 42,
                                        "reasoning": 7, "total": 149}}}),
    ])
    p = parse(good)
    check("R15: final message extracted from event stream",
          p["text"] == report_text and p["schema"] == "opencode-events-v1")
    check("R15: finish_reason and token usage captured",
          p["finish_reason"] == "stop" and p["usage"]["output"] == 42
          and p["usage"]["reasoning"] == 7)
    check("R15: extracted text carries no JSON envelope",
          '"sessionID"' not in p["text"] and not p["text"].startswith("{"))
    check("R15: stub detector clears the extracted report text",
          not mod._is_truncated_stub(p["text"]))

    truncated = good[: good.rindex("\n") + 30]  # cut mid-way through final line
    p = parse(truncated)
    check("R15: truncated final line skipped, earlier text survives",
          p["text"] == report_text and p["malformed_lines"] == 1,
          f"malformed={p['malformed_lines']}")

    noisy = "garbage not json\n" + good + "\n{\"half\": "
    p = parse(noisy)
    check("R15: malformed lines counted and skipped",
          p["text"] == report_text and p["malformed_lines"] == 2)

    errs = json.dumps({"type": "error", "timestamp": 1, "sessionID": "s",
                       "error": {"name": "UnknownError",
                                 "data": {"message": "boom"}}})
    p = parse(errs)
    check("R15: error-only stream yields errors and no text",
          p["errors"] and not p["text"])

    p = parse("# A plain markdown report\n\nNo JSON here.")
    check("R15: non-event output falls back to labeled plaintext",
          p["schema"] == "plaintext-fallback" and "plain markdown" in p["text"])

    updated = "\n".join([
        json.dumps({"type": "text", "timestamp": 1, "sessionID": "s",
                    "part": {"id": "p1", "type": "text", "text": "partial dr"}}),
        json.dumps({"type": "text", "timestamp": 2, "sessionID": "s",
                    "part": {"id": "p1", "type": "text", "text": "final draft"}}),
    ])
    p = parse(updated)
    check("R15: latest event per part id wins", p["text"] == "final draft")

    print()
    if FAILURES:
        print(f"R3/R4/R15: {len(FAILURES)} failure(s)")
        return 1
    print("R3/R4/R15: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
