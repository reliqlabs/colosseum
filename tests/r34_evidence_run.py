#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""R34: producer-trusted evidence records and Gate B artifact validation."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "evidence-run.ts"
GATE = REPO / "scripts" / "check_evidence_records.py"
FAILURES: list[str] = []

HARNESS = r"""
const [, , toolPath, projectRoot] = process.argv;
const mod = await import(toolPath);
const stub: any = {};
for (const key of ["optional", "array", "describe", "min", "max", "default", "nullable"]) stub[key] = () => stub;
const zod: any = new Proxy(stub, { get: (target, key) => key in target ? target[key] : () => stub });
let dirty = false;
const api: any = {
  cwd: projectRoot,
  zod,
  async exec(command: string, args: string[], options: any = {}) {
    if (command === "git" && args.join(" ") === "rev-parse HEAD") {
      return { stdout: "deadbeef\n", stderr: "", code: 0, killed: false };
    }
    if (command === "git" && args[0] === "status") {
      return { stdout: dirty ? " M src.ts\n" : "", stderr: "", code: 0, killed: false };
    }
    const child = Bun.spawn([command, ...args], { cwd: options.cwd, stdout: "pipe", stderr: "pipe" });
    const [stdout, stderr, code] = await Promise.all([
      new Response(child.stdout).text(),
      new Response(child.stderr).text(),
      child.exited,
    ]);
    return { stdout, stderr, code, killed: false };
  },
};
const tool = await mod.default(api);
const passing = await tool.execute("pass", {
  claim_id: "W1",
  command: ["sh", "-c", "echo 'test result: ok.'"],
  evidence_class: "test-witnessed",
  scope: "passing shell probe",
}, undefined, {}, undefined);
const failing = await tool.execute("fail", {
  claim_id: "B1",
  command: ["sh", "-c", "echo failed >&2; exit 7"],
  evidence_class: "bounded-checked",
  scope: "failing shell probe",
}, undefined, {}, undefined);
dirty = true;
const dirtyResult = await tool.execute("dirty", {
  claim_id: "D1", command: ["sh", "-c", "echo 'test result: ok.'"],
  evidence_class: "test-witnessed", scope: "dirty source probe",
}, undefined, {}, undefined);
dirty = false;
const customMarker = await tool.execute("custom", {
  claim_id: "C1", command: ["sh", "-c", "echo CUSTOM_OK"],
  evidence_class: "test-witnessed", scope: "custom marker probe", pass_marker: "CUSTOM_OK",
}, undefined, {}, undefined);
const relativeExecutable = await tool.execute("relative", {
  claim_id: "R1", command: ["./probe"], cwd: "sub",
  evidence_class: "test-witnessed", scope: "relative executable probe",
}, undefined, {}, undefined);
const intentDrift = await tool.execute("intent-drift", {
  claim_id: "I1",
  command: ["sh", "-c", "printf '# Changed Intent\\n' > .fv/intent.md; echo 'test result: ok.'"],
  evidence_class: "test-witnessed", scope: "intent drift probe",
}, undefined, {}, undefined);
let escapeError = "";
try {
  await tool.execute("escape", {
    claim_id: "E1", command: ["sh", "-c", "echo 'test result: ok.'"], cwd: "escape",
    evidence_class: "test-witnessed", scope: "symlink escape probe",
  }, undefined, {}, undefined);
} catch (error) { escapeError = String(error); }
console.log(JSON.stringify({
  passing: passing.details, failing: failing.details, dirty: dirtyResult.details,
  customMarker: customMarker.details, relativeExecutable: relativeExecutable.details,
  intentDrift: intentDrift.details, escapeError,
}));
"""


def check(label: str, condition: bool, detail: object = "") -> None:
    if condition:
        print(f"  [ok]   {label}")
    else:
        print(f"  [FAIL] {label}" + (f" ({detail})" if detail else ""))
        FAILURES.append(label)


def gate(record: Path, root: Path, required: str, manifest: Path | None = None) -> subprocess.CompletedProcess:
    command = ["python3", str(GATE), "--records", str(record), "--root", str(root),
               "--allow-unbound", "--json"]
    if manifest:
        command += ["--manifest", str(manifest)]
    else:
        command += ["--require", required]
    return subprocess.run(command, capture_output=True, text=True)


def main() -> int:
    if shutil.which("bun") is None:
        print("SKIP-FAIL: bun not on PATH")
        return 2
    with tempfile.TemporaryDirectory(prefix="r34-") as temporary:
        root = Path(temporary) / "project"
        state = root / ".fv"
        state.mkdir(parents=True)
        (state / "intent.md").write_text("# Intent\n")
        manifest = state / "obligations.json"
        manifest.write_text(json.dumps({
            "version": 1,
            "invariants": [{"id": "B1", "name": "inv_b1"}],
            "witnesses": [{"id": "W1", "name": "witness_w1"}],
        }))
        outside = Path(temporary) / "outside"
        outside.mkdir()
        (root / "escape").symlink_to(outside, target_is_directory=True)
        root_probe = root / "probe"
        root_probe.write_text("#!/bin/sh\necho root-probe\n")
        root_probe.chmod(0o755)
        sub = root / "sub"
        sub.mkdir()
        sub_probe = sub / "probe"
        sub_probe.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"--version\" ]; then echo sub-probe-v1; "
            "else echo 'test result: ok.'; fi\n"
        )
        sub_probe.chmod(0o755)
        harness = root / "harness.ts"
        harness.write_text(HARNESS)
        run = subprocess.run(
            ["bun", "run", str(harness), str(TOOL), str(root)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        lines = run.stdout.strip().splitlines()
        check("evidence tool executes under Bun", run.returncode == 0 and bool(lines), run.stderr)
        result = json.loads(lines[-1]) if lines else {}
        passing_path = state / "evidence" / "records" / "W1.json"
        failing_path = state / "evidence" / "records" / "B1.json"
        check("passing record persisted", passing_path.is_file())
        check("failing record persisted", failing_path.is_file())
        passing = json.loads(passing_path.read_text())
        failing = json.loads(failing_path.read_text())
        check("producer marks matching exit-zero probe PASS", passing["result"] == "PASS", result)
        check("dirty source cannot produce PASS evidence",
              result.get("dirty", {}).get("record", {}).get("result") == "FAIL", result)
        check("custom pass marker replaces the evidence-class marker",
              result.get("customMarker", {}).get("record", {}).get("result") == "PASS", result)
        check("intent drift during execution cannot produce PASS evidence",
              result.get("intentDrift", {}).get("record", {}).get("result") == "FAIL", result)
        check("producer records resolved executable identity",
              set(passing["bindings"]["toolchain_digests"]) ==
              {"executable", "sha256", "version", "version_exit_code"}, passing)
        relative_binding = result["relativeExecutable"]["record"]["bindings"]["toolchain_digests"]
        check("relative command executes the same binary whose digest is recorded",
              relative_binding["executable"] == str(sub_probe.resolve())
              and result["relativeExecutable"]["record"]["result"] == "PASS", relative_binding)
        custom_path = state / "evidence" / "records" / "C1.json"
        custom_checked = gate(custom_path, root, "C1")
        check("Gate B accepts a produced custom-marker PASS record",
              custom_checked.returncode == 0, custom_checked.stdout + custom_checked.stderr)
        check("cwd symlink escape rejected before execution",
              "inside the project root" in result.get("escapeError", ""), result)
        check("producer marks nonzero probe FAIL", failing["result"] == "FAIL", result)
        valid = gate(passing_path, root, "W1")
        check("Gate B accepts produced PASS record", valid.returncode == 0, valid.stdout + valid.stderr)
        failed = gate(failing_path, root, "B1")
        check("Gate B reports produced failing probe", failed.returncode == 1 and "FAILED" in failed.stdout, failed.stdout)

        missing = json.loads(passing_path.read_text())
        missing["bindings"]["raw_output_path"] = ".fv/evidence/raw/does-not-exist.log"
        missing_path = root / "missing.json"
        missing_path.write_text(json.dumps(missing))
        checked = gate(missing_path, root, "W1")
        check("missing raw artifact rejected", checked.returncode == 3 and "unresolvable raw artifact" in checked.stdout, checked.stdout)

        wrong = json.loads(passing_path.read_text())
        wrong["bindings"]["raw_output_hash"] = "0" * 64
        wrong_path = root / "wrong-hash.json"
        wrong_path.write_text(json.dumps(wrong))
        checked = gate(wrong_path, root, "W1")
        check("wrong raw hash rejected", checked.returncode == 3 and "raw output hash mismatch" in checked.stdout, checked.stdout)

        marker_raw = state / "evidence" / "raw" / "marker-absent.log"
        marker_raw.write_text("command completed\n--- fv-evidence: exit=0 ---\n")
        absent = json.loads(passing_path.read_text())
        absent["bindings"]["raw_output_path"] = str(marker_raw.relative_to(root))
        absent["bindings"]["raw_output_hash"] = hashlib.sha256(marker_raw.read_bytes()).hexdigest()
        absent_path = root / "marker-absent.json"
        absent_path.write_text(json.dumps(absent))
        checked = gate(absent_path, root, "W1")
        check("missing class marker rejected", checked.returncode == 3 and "PASS marker absent" in checked.stdout, checked.stdout)

        exit_raw = state / "evidence" / "raw" / "forged-exit.log"
        exit_raw.write_text("test result: ok.\n--- fv-evidence: exit=7 ---\n")
        forged = json.loads(passing_path.read_text())
        forged["bindings"]["raw_output_path"] = str(exit_raw.relative_to(root))
        forged["bindings"]["raw_output_hash"] = hashlib.sha256(exit_raw.read_bytes()).hexdigest()
        forged["bindings"]["configuration"] = {"pass_marker": ".*"}
        forged_path = root / "forged-exit.json"
        forged_path.write_text(json.dumps(forged))
        checked = gate(forged_path, root, "W1")
        check("record-controlled regex cannot mask nonzero exit",
              checked.returncode == 3 and "canonical exit=0 trailer" in checked.stdout,
              checked.stdout)
        conflicting_raw = state / "evidence" / "raw" / "conflicting-exit.log"
        conflicting_raw.write_text("test result: ok.\n--- fv-evidence: exit=7 ---\n--- fv-evidence: exit=0 ---\n")
        conflicting = json.loads(passing_path.read_text())
        conflicting["bindings"]["raw_output_path"] = str(conflicting_raw.relative_to(root))
        conflicting["bindings"]["raw_output_hash"] = hashlib.sha256(conflicting_raw.read_bytes()).hexdigest()
        conflicting_path = root / "conflicting-exit.json"
        conflicting_path.write_text(json.dumps(conflicting))
        checked = gate(conflicting_path, root, "W1")
        check("conflicting exit trailers rejected",
              checked.returncode == 3 and "one unique canonical exit=0 trailer" in checked.stdout,
              checked.stdout)

        incompatible = json.loads(passing_path.read_text())
        incompatible["claim_id"] = "B1"
        incompatible_path = root / "incompatible.json"
        incompatible_path.write_text(json.dumps(incompatible))
        checked = gate(incompatible_path, root, "", manifest)
        check("incompatible obligation class rejected", "incompatible evidence class" in checked.stdout, checked.stdout)

        fresh = Path(temporary) / "fresh"
        fresh_state = fresh / ".fv"
        fresh_state.mkdir(parents=True)
        fresh_intent = fresh_state / "intent.md"
        fresh_intent.write_text("# Intent\n")
        fresh_manifest = fresh_state / "obligations.json"
        fresh_manifest.write_text(json.dumps({"invariants": [], "witnesses": [{"id": "W1"}]}))
        source_file = fresh / "src.txt"
        source_file.write_text("clean\n")
        subprocess.run(["git", "init", "-q", str(fresh)], check=True)
        subprocess.run(["git", "-C", str(fresh), "config", "user.email", "r34@example.test"], check=True)
        subprocess.run(["git", "-C", str(fresh), "config", "user.name", "R34"], check=True)
        subprocess.run(["git", "-C", str(fresh), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(fresh), "commit", "-qm", "fixture"], check=True)
        fresh_head = subprocess.run(["git", "-C", str(fresh), "rev-parse", "HEAD"],
                                    capture_output=True, text=True, check=True).stdout.strip()
        fresh_raw = fresh_state / "evidence" / "raw.log"
        fresh_raw.parent.mkdir(parents=True)
        fresh_raw.write_text("test result: ok.\n--- fv-evidence: exit=0 ---\n")
        fresh_record = json.loads(passing_path.read_text())
        fresh_record["bindings"].update({
            "source_snapshot": fresh_head,
            "intent_hash": hashlib.sha256(fresh_intent.read_bytes()).hexdigest(),
            "obligation_manifest_hash": hashlib.sha256(fresh_manifest.read_bytes()).hexdigest(),
            "raw_output_path": str(fresh_raw.relative_to(fresh)),
            "raw_output_hash": hashlib.sha256(fresh_raw.read_bytes()).hexdigest(),
        })
        fresh_record_path = fresh_state / "evidence" / "record.json"
        fresh_record_path.write_text(json.dumps(fresh_record))
        current = subprocess.run(["python3", str(GATE), "--records", str(fresh_record_path),
                                  "--root", str(fresh), "--manifest", str(fresh_manifest), "--json"],
                                 capture_output=True, text=True)
        check("Gate B derives current source, intent, and manifest bindings",
              current.returncode == 0, current.stdout + current.stderr)
        source_file.write_text("dirty\n")
        dirty_current = subprocess.run(["python3", str(GATE), "--records", str(fresh_record_path),
                                        "--root", str(fresh), "--manifest", str(fresh_manifest), "--json"],
                                       capture_output=True, text=True)
        check("Gate B refuses current-state verification on dirty source",
              dirty_current.returncode == 2 and "source tree is dirty" in dirty_current.stdout,
              dirty_current.stdout + dirty_current.stderr)

    print()
    if FAILURES:
        print(f"R34: {len(FAILURES)} failure(s)")
        return 1
    print("R34: all assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
