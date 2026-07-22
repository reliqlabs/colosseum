#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""R30: OMP-native model fan-out is routed, isolated, and auditable."""
from __future__ import annotations

import importlib.util
import functools
import os
import json
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "skills" / "colosseum-adversarial" / "omp_fanout.py"
CONFIG = REPO / "scripts" / "dispatch.config.example.json"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    if ok:
        print(f"[ok] {label}")
    else:
        print(f"[FAIL] {label}: {detail}")
        FAILURES.append(label)


def load_helper():
    spec = importlib.util.spec_from_file_location("omp_fanout", HELPER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def raises(fn, text: str) -> bool:
    try:
        fn()
    except Exception as exc:
        return text in str(exc)
    return False


def serial_parallel(thunks):
    # The production bridge runs these concurrently. Serial execution keeps the
    # fixture deterministic while exercising the same failure-isolated thunks.
    return [thunk() for thunk in thunks]


def main() -> int:
    mod = load_helper()
    # Every run_omp_fanout call needs the isolation opt-in; inject it once so
    # the individual call sites stay readable. Refusal tests override it.
    mod.run_omp_fanout = functools.partial(
        mod.run_omp_fanout, allow_unverified_isolation=True)
    route = mod.load_omp_native_config(CONFIG)
    check("canonical OMP route resolves all four voices",
          [voice["id"] for voice in route["voices"]]
          == ["claude-agent", "gpt-5.6-sol", "glm-5.2", "kimi-k2.6"])
    check("canonical OMP route is explicitly uncalibrated",
          route["calibration"] == "pending")
    selected = mod.load_omp_native_config(
        CONFIG, selected_ids=["glm-5.2", "claude-agent"])
    check("explicit OMP voice order is preserved",
          [voice["id"] for voice in selected["voices"]]
          == ["glm-5.2", "claude-agent"])
    check("unknown OMP voice fails closed",
          raises(lambda: mod.load_omp_native_config(
              CONFIG, selected_ids=["not-registered"]), "not registered"))

    drifted = json.loads(CONFIG.read_text())
    drifted["omp_native"]["voices"][0]["model"] = "wrong/model"
    with tempfile.TemporaryDirectory(prefix="r30-config-") as td:
        bad_config = Path(td) / "dispatch.json"
        bad_config.write_text(json.dumps(drifted))
        check("OMP route hash catches model drift",
              raises(lambda: mod.load_omp_native_config(bad_config), "hash drift"))

    calls: list[tuple[str, str]] = []

    def fake_agent(prompt: str, **options):
        model = options["model"]
        calls.append((model, prompt))
        if model == selected["voices"][0]["model"]:
            raise RuntimeError("provider unavailable")
        voice_id = options["label"].removeprefix("omp-")
        return {
            "text": f"report from {model}",
            "output": f"report from {model}",
            "handle": f"agent://{voice_id}",
            "id": voice_id,
            "agent": options["agent"],
        }

    with tempfile.TemporaryDirectory(prefix="r30-run-") as td:
        root = Path(td)
        # A session whose documented header cwd == project_root: the gate's
        # trusted signal (PI_SESSION_FILE) for every run in this block.
        sess = root / "session.jsonl"
        sess.write_text('{"type":"title","v":1}\n'
                        + json.dumps({"type": "session", "id": "r30sess",
                                      "cwd": str(root)}) + "\n")
        os.environ["PI_SESSION_FILE"] = str(sess)
        target = root / "intent.md"
        target.write_text("# Intent\n")
        run_dir = root / ".colosseum" / "attacks" / "partial"
        summary = mod.run_omp_fanout(
            agent_fn=fake_agent,
            parallel_fn=serial_parallel,
            voices=selected["voices"],
            project_root=root,
            target_spec=target,
            prompt="TARGET_SPEC: intent.md",
            run_dir=run_dir,
            metadata={
                "profile": route["profile"],
                "route_hash": route["route_hash"],
                "calibration": route["calibration"],
                "phase": "attack",
            },
        )
        check("one failed voice does not sink surviving reports",
              summary["verdict"] == "PARTIAL" and summary["voices_ok"] == 1,
              summary)
        check("every requested OMP voice was invoked", len(calls) == 2, calls)
        statuses = {voice["id"]: voice["status"] for voice in summary["voices"]}
        check("failed provider is recorded as error",
              statuses == {"glm-5.2": "error", "claude-agent": "ok"}, statuses)
        check("successful report persists verbatim",
              (run_dir / "raw" / "omp-claude-agent.md").read_text()
              == f"report from {selected['voices'][1]['model']}")
        check("provider error persists independently",
              "provider unavailable" in
              (run_dir / "raw" / "omp-glm-5.2.error.txt").read_text())
        check("native bridge never invents finish reasons",
              all(voice["finish_reason"] is None for voice in summary["voices"]))
        check("summary is written last as parseable JSON",
              json.loads((run_dir / "summary.json").read_text())["verdict"]
              == "PARTIAL")
        check("preflight binds the target specification hash",
              summary["preflight"]["status"] == "ok"
              and summary["preflight"]["target_spec"] == "intent.md"
              and summary["preflight"]["target_spec_sha256"].startswith("sha256:"))
        meta = json.loads((run_dir / "meta.json").read_text())
        check("run metadata binds route and calibration",
              meta["metadata"]["route_hash"] == route["route_hash"]
              and meta["metadata"]["calibration"] == "pending")
        check("run directory cannot be overwritten",
              raises(lambda: mod.run_omp_fanout(
                  agent_fn=fake_agent,
                  parallel_fn=serial_parallel,
                  voices=selected["voices"],
                  project_root=root,
                  target_spec=target,
                  prompt="again",
                  run_dir=run_dir,
              ), "File exists"))

        def all_fail(_prompt: str, **_options):
            raise RuntimeError("offline")

        failed = mod.run_omp_fanout(
            agent_fn=all_fail,
            parallel_fn=serial_parallel,
            voices=selected["voices"],
            project_root=root,
            target_spec=target,
            prompt_by_voice={
                "glm-5.2": "critique A",
                "claude-agent": "critique B",
            },
            run_dir=root / ".colosseum" / "attacks" / "all-fail",
            metadata={"phase": "critique"},
        )
        check("all-failed native wave is INCOMPLETE",
              failed["verdict"] == "INCOMPLETE" and failed["voices_ok"] == 0)
        check("per-voice critique prompts persist verbatim",
              (root / ".colosseum" / "attacks" / "all-fail"
               / "prompts" / "glm-5.2.md").read_text()
              == "critique A")

        def mutate_target(_prompt: str, **_options):
            target.write_text("# Changed during dispatch\n")
            return "report against unstable target"

        unstable = mod.run_omp_fanout(
            agent_fn=mutate_target,
            parallel_fn=serial_parallel,
            voices=[selected["voices"][1]],
            project_root=root,
            target_spec=target,
            prompt="attack",
            run_dir=root / ".colosseum" / "attacks" / "target-drift",
        )
        check("target drift makes an otherwise successful wave INCOMPLETE",
              unstable["voices_ok"] == 1
              and unstable["verdict"] == "INCOMPLETE"
              and unstable["target_spec_stable"] is False)
        def exploding_parallel(_thunks):
            raise RuntimeError("wave crashed")

        crash_dir = root / ".colosseum" / "attacks" / "wave-crash"
        check("orchestration crash re-raises",
              raises(lambda: mod.run_omp_fanout(
                  agent_fn=fake_agent,
                  parallel_fn=exploding_parallel,
                  voices=selected["voices"],
                  project_root=root,
                  target_spec=target,
                  prompt="attack",
                  run_dir=crash_dir,
              ), "wave crashed"))
        crash = json.loads((crash_dir / "summary.json").read_text())
        check("orchestration crash still persists an INCOMPLETE summary",
              crash["verdict"] == "INCOMPLETE" and crash["voices_ok"] == 0
              and "wave crashed" in crash.get("orchestration_error", ""))

        def dropping_parallel(thunks):
            return [thunk() for thunk in thunks][:-1]

        drop_dir = root / ".colosseum" / "attacks" / "wave-mismatch"
        check("wave result-count mismatch re-raises",
              raises(lambda: mod.run_omp_fanout(
                  agent_fn=fake_agent,
                  parallel_fn=dropping_parallel,
                  voices=selected["voices"],
                  project_root=root,
                  target_spec=target,
                  prompt="attack",
                  run_dir=drop_dir,
              ), "results for"))
        drop = json.loads((drop_dir / "summary.json").read_text())
        check("wave mismatch still persists an INCOMPLETE summary",
              drop["verdict"] == "INCOMPLETE" and "orchestration_error" in drop)

        check("run stamps isolation unverified with session-root source",
              summary["isolation"]["status"] == "unverified"
              and summary["isolation"]["session_root_source"]
                  == "PI_SESSION_FILE session-header cwd"
              and Path(summary["isolation"]["session_root"]).resolve()
                  == root.resolve())
        check("meta stamps isolation unverified",
              meta["isolation"]["status"] == "unverified")
        acks = len(calls)
        check("missing isolation opt-in refuses before dispatch",
              raises(lambda: mod.run_omp_fanout(
                  agent_fn=fake_agent, parallel_fn=serial_parallel,
                  voices=selected["voices"], project_root=root, target_spec=target,
                  prompt="x", run_dir=root / ".colosseum" / "attacks" / "no-ack",
                  allow_unverified_isolation=False), "isolation is unverified")
              and len(calls) == acks)
        with tempfile.TemporaryDirectory(prefix="r30-otherroot-") as other:
            wrong = Path(other) / "s.jsonl"
            wrong.write_text(json.dumps(
                {"type": "session", "id": "w", "cwd": other}) + "\n")
            os.environ["PI_SESSION_FILE"] = str(wrong)
            m0 = len(calls)
            check("session root mismatch refuses before dispatch",
                  raises(lambda: mod.run_omp_fanout(
                      agent_fn=fake_agent, parallel_fn=serial_parallel,
                      voices=selected["voices"], project_root=root,
                      target_spec=target, prompt="x",
                      run_dir=root / ".colosseum" / "attacks" / "mismatch"),
                      "not project_root")
                  and len(calls) == m0)
        os.environ["PI_SESSION_FILE"] = str(sess)
        saved = os.environ.pop("PI_SESSION_FILE", None)
        m1 = len(calls)
        check("absent session metadata refuses before dispatch",
              raises(lambda: mod.run_omp_fanout(
                  agent_fn=fake_agent, parallel_fn=serial_parallel,
                  voices=selected["voices"], project_root=root, target_spec=target,
                  prompt="x", run_dir=root / ".colosseum" / "attacks" / "no-sess"),
                  "cannot confirm the OMP session root")
              and len(calls) == m1)
        if saved is not None:
            os.environ["PI_SESSION_FILE"] = saved
        (root / ".env").write_text("SECRET=value\n")
        blocked_dir = root / ".colosseum" / "attacks" / "blocked"
        calls_before = len(calls)
        blocked = raises(lambda: mod.run_omp_fanout(
            agent_fn=fake_agent,
            parallel_fn=serial_parallel,
            voices=selected["voices"],
            project_root=root,
            target_spec=target,
            prompt="attack",
            run_dir=blocked_dir,
        ), "preflight blocked")
        check("secret-bearing project fails before any model call",
              blocked and len(calls) == calls_before)
        check("blocked preflight remains auditable",
              json.loads((blocked_dir / "preflight.json").read_text())["status"]
              == "blocked")

    with tempfile.TemporaryDirectory(prefix="r30-scan-") as td:
        sroot = Path(td)
        (sroot / "clean.rs").write_text("fn main() {}\n")
        check("clean tree scans clean",
              mod.preflight_scan(sroot) == [], mod.preflight_scan(sroot))
        (sroot / "notes.txt").write_text(
            "context\n-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n")
        v = mod.preflight_scan(sroot)
        check("openssh key in a non-secret-named file is caught",
              any("private-key material" in x and "notes.txt" in x for x in v), v)
        (sroot / "backup.asc").write_text(
            "-----BEGIN PGP PRIVATE KEY BLOCK-----\nlQ...\n")
        v = mod.preflight_scan(sroot)
        check("pgp private-key block is caught",
              any("private-key material" in x and "backup.asc" in x for x in v), v)
        (sroot / "scanner_src.py").write_text(
            'M1 = b"PRIVATE KEY-----"\nM2 = b"PRIVATE KEY BLOCK"\n')
        v = mod.preflight_scan(sroot)
        check("marker constants without BEGIN armor are not flagged",
              not any("scanner_src.py" in x for x in v), v)
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            opaque = sroot / "opaque.bin"
            opaque.write_bytes(b"\x00" * 32)
            os.chmod(opaque, 0)
            try:
                v = mod.preflight_scan(sroot)
                check("unreadable file fails closed (recorded, not skipped)",
                      any("unreadable file" in x and "opaque.bin" in x for x in v), v)
            finally:
                os.chmod(opaque, 0o644)

    print()
    if FAILURES:
        print(f"R30: {len(FAILURES)} failure(s)")
        return 1
    print("R30: all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
