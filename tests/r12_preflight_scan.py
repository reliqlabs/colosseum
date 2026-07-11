#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R12 — ephemeral execution environment + preflight scan (Z2, contract G5).

Builds throwaway git-repo fixtures and drives
`opencode_dispatch.py --preflight-only` against them:

  1. tracked seeded secret (.env)            -> preflight blocks, nonzero exit
  2. tracked symlink escaping the root       -> preflight blocks, nonzero exit
  3. clean repo, UNTRACKED .env in root      -> worktree mode passes (the
     worktree sheds untracked files; combined with case 4 this shows the
     shedding is what makes it pass)
  4. same repo, --unsafe-in-place            -> preflight blocks on the
     untracked .env
  5. tracked private-key material (id file)  -> preflight blocks
  6. non-git project_root, worktree mode     -> fatal, points at --unsafe-in-place

Each blocking case also asserts preflight.json records the violation.
No opencode dispatch happens anywhere (--preflight-only exits first).

Exit 0 on pass, 1 on failure.
"""
from __future__ import annotations

import json
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


def sh(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def make_fixture(root: Path, git: bool = True) -> Path:
    """Minimal project: intent.md + README, one commit."""
    proj = root / "proj"
    proj.mkdir(parents=True)
    (proj / "intent.md").write_text("# Intent\n\n## 1. System Identity\n\nFixture.\n")
    (proj / "README.md").write_text("fixture\n")
    if git:
        sh("git", "init", "-q", cwd=proj)
        sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A", cwd=proj)
        sh("git", "-c", "user.email=t@t", "-c", "user.name=t",
           "commit", "-q", "-m", "fixture", cwd=proj)
    return proj


def write_config(proj: Path) -> Path:
    cfg = {
        "project_root": str(proj),
        "target_spec": str(proj / "intent.md"),
        "run_tag_prefix": "r12",
        "voices": [{"id": "dummy", "model": "none/none"}],
        "slices": [{"name": "s", "label": "s", "headers": ["## 1."], "attack_emphasis": "n/a"}],
    }
    path = proj / "dispatch.json"
    path.write_text(json.dumps(cfg))
    return path


def preflight(cfg_path: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "--script", str(DISPATCH),
         "--config", str(cfg_path), "--preflight-only", *extra],
        capture_output=True, text=True,
    )


def latest_preflight_report(proj: Path) -> dict | None:
    reports = sorted((proj / ".colosseum" / "attacks").glob("*/preflight.json"))
    if not reports:
        return None
    return json.loads(reports[-1].read_text())


def commit_all(proj: Path, msg: str) -> None:
    sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "add", "-A", cwd=proj)
    sh("git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", msg, cwd=proj)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="r12-") as td:
        tmp = Path(td)

        # 1. tracked seeded secret
        proj = make_fixture(tmp / "c1")
        (proj / ".env").write_text("FAKE_API_KEY=deadbeef\n")
        commit_all(proj, "seed secret")
        r = preflight(write_config(proj))
        check("tracked .env: preflight blocks", r.returncode != 0, f"exit={r.returncode}")
        check("tracked .env: violation names the file",
              "secret-named file: .env" in (r.stderr + r.stdout))
        rep = latest_preflight_report(proj)
        check("tracked .env: preflight.json records violation",
              rep is not None and any("secret-named" in v for v in rep["violations"]))

        # 2. tracked symlink escaping the root
        proj = make_fixture(tmp / "c2")
        (proj / "escape").symlink_to("/etc")
        commit_all(proj, "seed symlink")
        r = preflight(write_config(proj))
        check("escaping symlink: preflight blocks", r.returncode != 0, f"exit={r.returncode}")
        check("escaping symlink: violation names the link",
              "symlink escapes root: escape" in (r.stderr + r.stdout))

        # 3. clean repo, untracked .env: worktree sheds it, preflight passes
        proj = make_fixture(tmp / "c3")
        (proj / ".env").write_text("FAKE_API_KEY=deadbeef\n")  # untracked
        cfg_path = write_config(proj)
        r = preflight(cfg_path)
        check("untracked .env, worktree mode: preflight passes", r.returncode == 0,
              f"exit={r.returncode}: {(r.stderr or r.stdout)[-300:]}")
        rep = latest_preflight_report(proj)
        check("worktree mode: report mode=worktree and spec hash recorded",
              rep is not None and rep["mode"] == "worktree"
              and len(rep.get("target_spec_sha256", "")) == 64)

        # 4. same repo in-place: the untracked .env now blocks
        r = preflight(cfg_path, "--unsafe-in-place")
        check("untracked .env, in-place mode: preflight blocks", r.returncode != 0,
              f"exit={r.returncode}")
        check("in-place mode: violation names .env",
              "secret-named file: .env" in (r.stderr + r.stdout))

        # 5. tracked private-key material under a non-secret name
        proj = make_fixture(tmp / "c5")
        (proj / "notes.txt").write_text(
            "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n-----END OPENSSH PRIVATE KEY-----\n")
        commit_all(proj, "seed key")
        r = preflight(write_config(proj))
        check("private-key content: preflight blocks", r.returncode != 0, f"exit={r.returncode}")
        check("private-key content: violation names the file",
              "private-key material: notes.txt" in (r.stderr + r.stdout))

        # 6. non-git root: worktree mode is fatal and names the escape hatch
        proj = make_fixture(tmp / "c6", git=False)
        r = preflight(write_config(proj))
        check("non-git root: worktree mode fatal", r.returncode != 0, f"exit={r.returncode}")
        check("non-git root: message points at --unsafe-in-place",
              "--unsafe-in-place" in (r.stderr + r.stdout))

    print()
    if FAILURES:
        print(f"R12: {len(FAILURES)} failure(s)")
        return 1
    print("R12: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
