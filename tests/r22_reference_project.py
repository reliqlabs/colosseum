#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
R22 — reference project end-to-end (exit criterion 9).

The known-good `jobq` project (tests/fixtures/r22/project) passes every
gate: the tested pyramid profile, Gate A reference integrity, quint
verify over B1-B4 plus the W1 witness search, ITF conformance replay
through the real library, and Gate B over G1 records GENERATED LIVE from
those very runs (no canned evidence). Known-bad mutations, each applied
to its own temp copy, fail at exactly their intended gate while at least
one other gate stays green — failure is localized, never diffuse.

Requires cargo (exit 2 if absent). quint-side gates run when quint is on
PATH; without it the cargo-side asserts still run and the suite exits 2
(SKIP-FAIL): an environment that cannot exercise the spec gates has not
passed R22. Exit 0 pass, 1 fail, 2 toolchain unavailable.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "r22"
PYRAMID = REPO / "scripts" / "pyramid_run.py"
GATE_A = REPO / "scripts" / "check_ledger_references.py"
GATE_B = REPO / "scripts" / "check_evidence_records.py"
REPLAY = REPO / "scripts" / "itf_replay.py"
FAILURES: list[str] = []

VERIFY_CMD = ["quint", "verify", "--invariant=inv_all", "--max-steps=12"]
WITNESS_CMD = ["quint", "run", "--invariant=witness_w1_negated",
               "--max-steps=8", "--max-samples=200", "--seed=0x1"]


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  [ok]   {label}")
    else:
        suffix = f" ({detail})" if detail else ""
        print(f"  [FAIL] {label}{suffix}")
        FAILURES.append(label)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600, **kw)


def copy_tree(dst: Path) -> Path:
    """Copy the whole r22 tree (project + adapter + conformance config)
    without build artifacts or stale verify reports."""
    shutil.copytree(FIXTURE, dst,
                    ignore=shutil.ignore_patterns("target", "verify"))
    return dst


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def project_snapshot(project: Path) -> str:
    """Deterministic content hash over the project's tracked-shape files."""
    h = hashlib.sha256()
    for p in sorted(project.rglob("*")):
        if p.is_file() and "target" not in p.parts and "verify" not in p.parts:
            h.update(str(p.relative_to(project)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:12] + "+fixture"


def make_records(project: Path, quint_version: str, verify_out: str,
                 witness_out: str, spec_rel: str) -> list[dict]:
    """G1 records constructed from the runs this suite actually performed."""
    snapshot = project_snapshot(project)
    intent_hash = sha256_file(project / "INTENT.md")
    manifest_hash = sha256_file(project / ".colosseum" / "obligations.json")
    digests = {"quint": quint_version}
    common = {
        "source_snapshot": snapshot,
        "intent_hash": intent_hash,
        "obligation_manifest_hash": manifest_hash,
        "profile": "bounded",
        "required_targets": ["B1", "B2", "B3", "B4", "W1"],
        "environment_policy": "r22-fixture-local",
        "toolchain_digests": digests,
        "parser_schema_version": f"quint-cli-{quint_version}",
    }
    records = []
    for cid in ("B1", "B2", "B3", "B4"):
        records.append({
            "claim_id": cid,
            "required": True,
            "evidence_class": "bounded-checked",
            "result": "PASS",
            "scope": "inv_all under bound 12, Apalache via quint verify",
            "bindings": {
                **common,
                "command": " ".join(VERIFY_CMD + [spec_rel]),
                "configuration": {"max_steps": 12},
                "seeds": None,
                "raw_output_hash": hashlib.sha256(verify_out.encode()).hexdigest(),
                "run_id": f"r22-verify-{cid}",
            },
            "waiver": None,
        })
    records.append({
        "claim_id": "W1",
        "required": True,
        "evidence_class": "test-witnessed",
        "result": "PASS",
        "scope": "witness trace reaching done>0, seeded run (0x1, 200 samples, depth 8)",
        "bindings": {
            **common,
            "command": " ".join(WITNESS_CMD + [spec_rel]),
            "configuration": {"max_steps": 8, "max_samples": 200},
            "seeds": "0x1",
            "raw_output_hash": hashlib.sha256(witness_out.encode()).hexdigest(),
            "run_id": "r22-witness-W1",
        },
        "waiver": None,
    })
    return records


def gate_b(records: list[dict], manifest: Path, tmp: Path, tag: str) -> subprocess.CompletedProcess:
    rec_dir = tmp / f"records-{tag}"
    rec_dir.mkdir()
    (rec_dir / "records.json").write_text(json.dumps(records, indent=2))
    return run([str(GATE_B), "--records", str(rec_dir), "--manifest", str(manifest)])


def main() -> int:
    if shutil.which("cargo") is None:
        print("SKIP-FAIL: cargo not on PATH; R22 cannot run", file=sys.stderr)
        return 2
    have_quint = shutil.which("quint") is not None

    with tempfile.TemporaryDirectory(prefix="r22-") as td:
        tmp = Path(td)
        good = copy_tree(tmp / "good")
        project = good / "project"
        ledger = project / ".colosseum" / "ledger.md"
        manifest = project / ".colosseum" / "obligations.json"

        # ── Part 1, cargo side: the known-good project passes ────────────
        p = run([str(PYRAMID), "--crate", str(project), "--profile", "tested"])
        out = p.stdout + p.stderr
        check("good: pyramid tested -> VERIFIED[tested]",
              p.returncode == 0 and "VERIFIED[tested]" in out, out[-300:])
        check("good: pyramid emits no bare VERIFIED",
              not re.search(r"VERIFIED(?!\[)", out))

        p = run([str(GATE_A), str(ledger)])
        check("good: Gate A reference integrity passes", p.returncode == 0,
              (p.stdout + p.stderr)[-300:])

        # ── Part 2, cargo side: mutations fail at their intended gate ────
        # Ledger drift: a comment at the top of queue.rs shifts every cited
        # line; Gate A must fail on the content hash, cargo tests still pass.
        drift = copy_tree(tmp / "drift")
        qrs = drift / "project" / "src" / "queue.rs"
        qrs.write_text("// drift: inserted line shifts all citations below\n"
                       + qrs.read_text())
        p = run([str(GATE_A), str(drift / "project" / ".colosseum" / "ledger.md")])
        check("drift: Gate A fails", p.returncode != 0)
        check("drift: names the content-hash mismatch",
              "content hash mismatch" in (p.stdout + p.stderr))
        p = run(["cargo", "test", "--quiet"], cwd=drift / "project")
        check("drift: other gate (cargo test) still green", p.returncode == 0)

        # Floors regression: strip the in-file test module; the tested
        # profile must FAIL at floors, and the crate still compiles.
        floors = copy_tree(tmp / "floors")
        qrs = floors / "project" / "src" / "queue.rs"
        src = qrs.read_text()
        stripped = re.sub(r"#\[cfg\(test\)\]\nmod tests \{.*?\n\}\n", "", src,
                          flags=re.DOTALL)
        check("floors: mutation removed the test module", stripped != src)
        qrs.write_text(stripped)
        p = run(["cargo", "check", "--quiet"], cwd=floors / "project")
        check("floors: mutated crate still compiles", p.returncode == 0,
              p.stderr[-300:])
        p = run([str(PYRAMID), "--crate", str(floors / "project"),
                 "--profile", "tested"])
        out = p.stdout + p.stderr
        check("floors: pyramid tested -> FAILED", p.returncode == 1, out[-300:])
        check("floors: failure names the floors layer",
              "floors" in out and "FAILED" in out)

        if not have_quint:
            print("\nSKIP-FAIL: quint not on PATH; spec gates (verify, witness, "
                  "conformance, Gate B live records) not exercised — an "
                  "environment that cannot run them has not passed R22",
                  file=sys.stderr)
            return 2

        # ── Part 1, quint side ───────────────────────────────────────────
        spec = project / "specs" / "jobq.qnt"
        qv = run(["quint", "--version"])
        quint_version = qv.stdout.strip() or "unknown"

        p = run(VERIFY_CMD + [str(spec)])
        verify_out = p.stdout + p.stderr
        check("good: quint verify inv_all passes (depth 12)", p.returncode == 0,
              verify_out[-300:])

        p = run(WITNESS_CMD + [str(spec)])
        witness_out = p.stdout + p.stderr
        check("good: witness search exhibits done>0 (violation of negation)",
              p.returncode != 0 and "violat" in witness_out.lower())

        p = run(["cargo", "build", "--quiet"], cwd=good / "adapter")
        check("good: adapter builds against the real library", p.returncode == 0,
              p.stderr[-300:])
        p = run([str(REPLAY), "--config", str(good / "conformance.json")])
        out = p.stdout + p.stderr
        check("good: conformance replay passes", p.returncode == 0, out[-300:])
        check("good: label is conformance-tested[<scope>]",
              "conformance-tested[" in out)
        check("good: REFINEMENT_VERIFIED appears nowhere",
              "REFINEMENT_VERIFIED" not in out)

        # Gate B over records generated from the runs above.
        spec_rel = "specs/jobq.qnt"
        records = make_records(project, quint_version, verify_out,
                               witness_out, spec_rel)
        p = gate_b(records, manifest, tmp, "good")
        out = p.stdout + p.stderr
        check("good: Gate B verdict is scoped VERIFIED[...]",
              p.returncode == 0 and "VERIFIED[" in out, out[-300:])
        check("good: Gate B emits no bare VERIFIED",
              not re.search(r"VERIFIED(?!\[)", out))

        # ── Part 2, evidence mutations (pure JSON) ───────────────────────
        broken = json.loads(json.dumps(records))
        del broken[1]["bindings"]["raw_output_hash"]
        p = gate_b(broken, manifest, tmp, "missing-field")
        out = p.stdout + p.stderr
        check("evidence: missing binding field -> INCOMPLETE (exit 3)",
              p.returncode == 3, out[-300:])
        check("evidence: the missing field is named",
              "raw_output_hash" in out)

        failed = json.loads(json.dumps(records))
        failed[2]["result"] = "FAIL"
        p = gate_b(failed, manifest, tmp, "fail-result")
        check("evidence: FAIL result -> FAILED (exit 1)", p.returncode == 1)

        # ── Part 2, spec weakening: quint verify catches it ──────────────
        weak = copy_tree(tmp / "weak")
        wspec = weak / "project" / "specs" / "jobq.qnt"
        text = wspec.read_text()
        weakened = text.replace("attempts < MAX_ATTEMPTS,",
                                "attempts <= MAX_ATTEMPTS,")
        check("weak: mutation applied to fail_retry guard", weakened != text)
        wspec.write_text(weakened)
        p = run(VERIFY_CMD + [str(wspec)])
        out = p.stdout + p.stderr
        check("weak: quint verify finds the violation", p.returncode != 0,
              out[-300:])
        p = run([str(GATE_A),
                 str(weak / "project" / ".colosseum" / "ledger.md")])
        check("weak: other gate (Gate A) still green (guard line not cited, "
              "no lines shifted)", p.returncode == 0)

        # ── Part 2, conformance divergence: replay catches it ────────────
        div = copy_tree(tmp / "div")
        dqrs = div / "project" / "src" / "queue.rs"
        text = dqrs.read_text()
        diverged = text.replace("        self.submitted += 1;\n",
                                "        // submitted increment dropped\n")
        check("div: mutation applied to submit()", diverged != text)
        dqrs.write_text(diverged)
        p = run(["cargo", "build", "--quiet"], cwd=div / "adapter")
        check("div: mutated crate still compiles into the adapter",
              p.returncode == 0, p.stderr[-300:])
        p = run([str(REPLAY), "--config", str(div / "conformance.json")])
        out = p.stdout + p.stderr
        check("div: replay fails", p.returncode != 0, out[-300:])
        check("div: divergence named with trace and step",
              "divergence at" in out and "step" in out)
        p = run([str(GATE_A),
                 str(div / "project" / ".colosseum" / "ledger.md")])
        check("div: other gate (Gate A) still green (same-position "
              "replacement, cited lines unchanged)", p.returncode == 0)

    print()
    if FAILURES:
        print(f"R22: {len(FAILURES)} failure(s)")
        return 1
    print("R22: all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
