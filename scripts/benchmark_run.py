#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
benchmark_run: the pre-registered ablation-arm runner (roadmap M3).

Runs the five arms fixed in docs/benchmark-protocol.md against one seeded
target and scores each arm with scripts/recall_score.py. The protocol is
pre-registered; this runner implements exactly its design and invents no
numbers. It is the "benchmark RUN" the protocol lists as pending: it needs
live multi-model dispatch, which it reaches through ONE dispatch abstraction
so a test can substitute a stub executable and drive every arm offline.

ARMS (docs/benchmark-protocol.md, cheapest to richest)
    ordinary      one voice, a NEUTRAL reviewer prompt (not the adversarial
                  instructions), same output contract. The floor.
    single        one voice, the adversarial REVIEW-INSTRUCTIONS as-is.
    repeated      the same voice run --repeats N times (default 3), each
                  pass an independent dispatch, kept SEPARATE for scoring
                  (self-ensemble; isolates sampling diversity).
    multi-family  each panel voice once, adversarial instructions.
    adversarial   multi-family plus ONE critique round: each voice is shown
                  the deduped union of the OTHER voices' round-1 findings,
                  blinded to authorship, and may add or withdraw. Round-2
                  outputs are recorded and scored separately from round 1.

DISPATCH (the single model-call surface)
    Every model call goes through Dispatcher.run(). It shells out to a
    command template, default
        opencode run --model {model} --agent spec-adversary {prompt}
    with cwd = the --targets dir. {model} and {prompt} are substituted into
    the argv tokens (no shell, so the prompt is one argv element and is not
    re-split). --dispatch-cmd overrides the template; that is how the test
    swaps in a stub. No other code path invokes a model.

BLINDING
    The corpus file is NEVER read by this runner and never enters a prompt
    or the target dir. It is passed by PATH to recall_score.py, which is the
    only reader, at scoring time. Critique-round unions carry finding fields
    only (file/line/category/severity/title); voice authorship is stripped.

PARSING (reused from calibration/2026-07-13-r1/parse_outputs.py)
    A voice's stdout is scanned for a fenced ```json array; the LAST valid
    block wins, with a bare top-level array as fallback. A dispatch that
    exits nonzero or yields no parseable block is ERRORED: it is recorded in
    the arm's errored map and excluded from detections, never scored as a
    zero-recall voice (an errored run is not a zero run).

OUTPUT (under --out)
    <arm>/raw/...            raw stdout + prompt per dispatch (errors -> .err)
    <arm>/detections.json    {voice_or_pass_key: [detections]} scored map
    <arm>/recall.json        recall_score --json output for the arm
    adversarial/ also carries raw/round1, raw/round2, critique/<voice>.prompt
      (the blinded union each voice saw), detections.round1.json, and
      recall.round1.json.
    summary.json             per-arm recall, per-voice contribution, error
      log, and cost placeholders. Token/cost fields are null unless a
      dispatch supplies token data; numbers are never invented.

EXIT CODES
    0  every requested arm ran and scored
    2  usage / config error (bad args, missing corpus/targets/instructions)
    3  INCOMPLETE: an arm could not run (dispatcher binary missing, an arm
       had zero successful dispatches, or recall_score could not score it).
       Never a fake pass.

DEGREES OF FREEDOM (documented per the protocol's instruction; kept conservative)
    1. Prompt construction. The protocol names the arms but not the exact
       prompt text. Adversarial arms dispatch REVIEW-INSTRUCTIONS.md
       verbatim ("as-is"). The ordinary arm keeps the SAME output contract
       (the reporting-format section, split at the first heading matching
       `#+ reporting`, case-insensitive) but replaces the adversarial
       framing with a neutral reviewer preamble. If no reporting heading is
       found, the whole file is used and a warning is printed.
    2. Critique round. Exactly one round (the protocol says "one critique
       round"). Every panel voice is dispatched in round 2, including one
       that errored in round 1, so a transient round-1 failure does not
       permanently bench a voice. A voice's round-2 union excludes its own
       round-1 findings and is deduped by (file,line,category,severity,title).
    3. Scoring keys. repeated-arm passes are keyed `<voice>#passK` so
       recall_score reports both per-pass recall and their union. The
       adversarial arm is scored on round-2 detections; round 1 is scored
       separately into recall.round1.json.
    4. An arm with zero successful dispatches is INCOMPLETE, not a scored
       0.0. recall_score would happily score an empty map as zero, which
       would misreport "could not run" as "ran and found nothing".
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
RECALL_SCORE = SCRIPTS_DIR / "recall_score.py"

ARMS = ["ordinary", "single", "repeated", "multi-family", "adversarial"]
DEFAULT_DISPATCH = "opencode run --model {model} --agent spec-adversary {prompt}"

FENCE = re.compile(r"```json\s*(\[.*?\])\s*```", re.DOTALL)
REQUIRED = {"file", "line", "category", "severity", "title"}
FIELDS = ("file", "line", "category", "severity", "title")

# Marker phrases the arm prompts carry. Kept stable and documented so a stub
# dispatcher can distinguish arms; they change no real model's behaviour.
ORDINARY_MARK = "This is an ordinary, non-adversarial code review."
CRITIQUE_MARK = "Candidate findings from other reviewers (authorship withheld):"

ORDINARY_PREAMBLE = f"""\
{ORDINARY_MARK}

You are reviewing the crate in the current working directory. Read INTENT.md
(the behavioral contract) and every source file, then report the defects a
careful reviewer would flag. This is a routine review, not a red-team pass:
report what you actually find and can ground in specific lines.

Use the reporting format below.
"""


class DispatcherMissing(Exception):
    """The dispatch binary is absent; the run is INCOMPLETE, not a no-op."""


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ─────────────────────────────────────────────────────────────────────────
# Parsing (fenced-json convention, per the module docstring)
# ─────────────────────────────────────────────────────────────────────────

def parse_findings(text: str) -> list[dict] | None:
    """Last fenced json array wins; bare top-level array is the fallback.
    Returns a list of well-formed findings, or None when nothing parses
    (which the caller records as an errored dispatch, not a zero)."""
    parsed = None
    for candidate in reversed(FENCE.findall(text)):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            parsed = data
            break
    if parsed is None:
        try:
            data = json.loads(text.strip())
            if isinstance(data, list):
                parsed = data
        except json.JSONDecodeError:
            pass
    if parsed is None:
        return None
    findings = []
    for f in parsed:
        if isinstance(f, dict) and REQUIRED <= set(f) and isinstance(f.get("line"), int):
            findings.append({k: f[k] for k in FIELDS})
    return findings


def dedup(findings: list[dict]) -> list[dict]:
    seen, out = set(), []
    for f in findings:
        key = tuple(f.get(k) for k in FIELDS)
        if key not in seen:
            seen.add(key)
            out.append({k: f.get(k) for k in FIELDS})
    return out


# ─────────────────────────────────────────────────────────────────────────
# Dispatch
# ─────────────────────────────────────────────────────────────────────────

class Dispatcher:
    def __init__(self, template: str, cwd: Path, timeout: int):
        self.tokens = shlex.split(template)
        if not self.tokens:
            sys.exit("error: --dispatch-cmd is empty")
        self.cwd = str(cwd)
        self.timeout = timeout

    def binary(self) -> str:
        return self.tokens[0]

    def available(self) -> bool:
        b = self.binary()
        return shutil.which(b) is not None or Path(b).exists()

    def argv(self, model: str, prompt: str) -> list[str]:
        return [t.replace("{model}", model).replace("{prompt}", prompt)
                for t in self.tokens]

    def display(self, model: str, prompt: str) -> str:
        shown = [(t.replace("{model}", model)
                  .replace("{prompt}", f"<prompt:{len(prompt)}c>"))
                 for t in self.tokens]
        return " ".join(shlex.quote(t) for t in shown)

    def run(self, model: str, prompt: str) -> dict:
        argv = self.argv(model, prompt)
        # opencode resolves its project from $PWD, not getcwd; subprocess
        # cwd= alone leaves the parent's stale PWD and the dispatch
        # server-errors. Keep them consistent.
        env = {**os.environ, "PWD": str(self.cwd)}
        t0 = time.monotonic()
        try:
            proc = subprocess.run(argv, cwd=self.cwd, env=env,
                                  capture_output=True,
                                  text=True, timeout=self.timeout)
        except FileNotFoundError as e:
            raise DispatcherMissing(str(e))
        except subprocess.TimeoutExpired:
            return {"error": f"timeout after {self.timeout}s", "text": ""}
        elapsed = time.monotonic() - t0
        if proc.returncode != 0:
            return {"error": f"exit {proc.returncode}: {proc.stderr.strip()[:300]}",
                    "text": proc.stdout, "elapsed": elapsed}
        return {"text": proc.stdout, "elapsed": elapsed}


def _fslug(key: str) -> str:
    """Voice ids double as raw-artifact filenames but may carry path
    separators (`openai/gpt-5.6-sol`, `...@cf/...`); slug them for the
    filesystem only. Detection-map keys keep the full id."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", key)


def dispatch_and_parse(dispatcher: Dispatcher, model: str, prompt: str,
                       raw_dir: Path, key: str) -> tuple[list[dict] | None, str | None]:
    """Run one dispatch, persist raw stdout + prompt, and parse. Returns
    (findings, None) on success or (None, reason) on an errored dispatch."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    stem = _fslug(key)
    (raw_dir / f"{stem}.prompt").write_text(prompt)
    res = dispatcher.run(model, prompt)
    text = res.get("text") or ""
    (raw_dir / f"{stem}.out").write_text(text)
    if "error" in res:
        (raw_dir / f"{stem}.err").write_text(res["error"])
        return None, res["error"]
    findings = parse_findings(text)
    if findings is None:
        reason = "no parseable json findings block"
        (raw_dir / f"{stem}.err").write_text(reason)
        return None, reason
    return findings, None


# ─────────────────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────────────────

def split_contract(instructions: str) -> str:
    """The output contract = the reporting-format section onward, so the
    ordinary arm can share it. Split at the first `#+ reporting` heading."""
    lines = instructions.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^#+\s*reporting", line.strip(), re.I):
            return "\n".join(lines[i:])
    log("warning: no `#+ reporting` heading in REVIEW-INSTRUCTIONS.md; "
        "ordinary arm falls back to the full instructions")
    return instructions


def ordinary_prompt(contract: str) -> str:
    return f"{ORDINARY_PREAMBLE}\n{contract}"


def critique_prompt(instructions: str, union: list[dict]) -> str:
    union_json = json.dumps(union, indent=2)
    return (
        f"{instructions}\n\n---\n\n"
        "You have completed one review pass of this crate. Below are candidate "
        "findings raised by OTHER reviewers of the same crate. Their authorship "
        "is withheld; treat each as a hypothesis to verify against the code, not "
        "as an authority.\n\n"
        f"{CRITIQUE_MARK}\n"
        f"```json\n{union_json}\n```\n\n"
        "Re-review the crate with these in mind. You MAY add findings you can "
        "now substantiate and MAY decline any candidate you judge wrong; a "
        "candidate you do not include is treated as withdrawn. Emit your FINAL "
        "findings list in the JSON contract above. Only your final JSON block "
        "is scored.\n"
    )


# ─────────────────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────────────────

def score(corpus: Path, detections: dict, det_path: Path,
          recall_path: Path) -> tuple[dict | None, str | None]:
    det_path.write_text(json.dumps(detections, indent=2))
    proc = subprocess.run(
        ["uv", "run", "--script", str(RECALL_SCORE),
         "--corpus", str(corpus), "--detections", str(det_path), "--json"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        return None, f"recall_score exit {proc.returncode}: {proc.stderr.strip()[:300]}"
    try:
        recall = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return None, f"recall_score emitted unparseable json: {e}"
    recall_path.write_text(json.dumps(recall, indent=2))
    return recall, None


def arm_entry(recall: dict | None, errored: dict, dispatches: int,
              status: str, reason: str | None = None) -> dict:
    entry = {
        "status": status,
        "dispatches": dispatches,
        "successful": dispatches - len(errored),
        "errored": errored,
        # Cost placeholders: the default dispatch emits plain text with no
        # token accounting, so these stay null. Never invented.
        "tokens": None,
        "cost_per_confirmed_defect": None,
    }
    if reason:
        entry["reason"] = reason
    if recall is not None:
        entry["panel_union_recall"] = recall["panel_union_recall"]
        entry["shared_blind_spot"] = recall["shared_blind_spot"]
        entry["shared_blind_spot_count"] = recall["shared_blind_spot_count"]
        entry["per_voice"] = recall["per_voice"]
    return entry


# ─────────────────────────────────────────────────────────────────────────
# Arms
# ─────────────────────────────────────────────────────────────────────────

def run_simple_arm(name: str, dispatcher: Dispatcher, voice: str, prompt: str,
                   out_arm: Path, corpus: Path, dispatches: list) -> dict:
    """ordinary / single: one voice, one dispatch."""
    log(f"[{name}] dispatching voice {voice}")
    findings, err = dispatch_and_parse(dispatcher, voice, prompt,
                                       out_arm / "raw", voice)
    dispatches.append((name, voice))
    errored, detections = {}, {}
    if err:
        errored[voice] = err
        return arm_entry(None, errored, 1, "INCOMPLETE",
                         "the arm's only voice errored; nothing to score")
    detections[voice] = findings
    recall, serr = score(corpus, detections, out_arm / "detections.json",
                         out_arm / "recall.json")
    if serr:
        return arm_entry(None, errored, 1, "INCOMPLETE", serr)
    return arm_entry(recall, errored, 1, "OK")


def run_repeated_arm(dispatcher: Dispatcher, voice: str, prompt: str, repeats: int,
                     out_arm: Path, corpus: Path, dispatches: list) -> dict:
    """repeated: the same voice, N independent passes kept separate."""
    errored, detections = {}, {}
    for i in range(1, repeats + 1):
        key = f"{voice}#pass{i}"
        log(f"[repeated] dispatching {key}")
        findings, err = dispatch_and_parse(dispatcher, voice, prompt,
                                           out_arm / "raw", key)
        dispatches.append(("repeated", key))
        if err:
            errored[key] = err
        else:
            detections[key] = findings
    if not detections:
        return arm_entry(None, errored, repeats, "INCOMPLETE",
                         "every pass errored; nothing to score")
    recall, serr = score(corpus, detections, out_arm / "detections.json",
                         out_arm / "recall.json")
    if serr:
        return arm_entry(None, errored, repeats, "INCOMPLETE", serr)
    return arm_entry(recall, errored, repeats, "OK")


def run_panel_round(dispatcher: Dispatcher, voices: list[str],
                    prompt_for, raw_dir: Path, dispatches_tag: str,
                    dispatches: list) -> tuple[dict, dict]:
    """One pass over the panel. prompt_for(voice) yields that voice's prompt.
    Returns (detections, errored)."""
    detections, errored = {}, {}
    for v in voices:
        log(f"[{dispatches_tag}] dispatching voice {v}")
        findings, err = dispatch_and_parse(dispatcher, v, prompt_for(v), raw_dir, v)
        dispatches.append((dispatches_tag, v))
        if err:
            errored[v] = err
        else:
            detections[v] = findings
    return detections, errored


def run_multi_arm(dispatcher: Dispatcher, voices: list[str], prompt: str,
                  out_arm: Path, corpus: Path, dispatches: list) -> dict:
    detections, errored = run_panel_round(
        dispatcher, voices, lambda v: prompt, out_arm / "raw",
        "multi-family", dispatches)
    if not detections:
        return arm_entry(None, errored, len(voices), "INCOMPLETE",
                         "every panel voice errored; nothing to score")
    recall, serr = score(corpus, detections, out_arm / "detections.json",
                         out_arm / "recall.json")
    if serr:
        return arm_entry(None, errored, len(voices), "INCOMPLETE", serr)
    return arm_entry(recall, errored, len(voices), "OK")


def run_adversarial_arm(dispatcher: Dispatcher, voices: list[str], instructions: str,
                        out_arm: Path, corpus: Path, dispatches: list) -> dict:
    # Round 1: the multi-family pass.
    r1_det, r1_err = run_panel_round(
        dispatcher, voices, lambda v: instructions, out_arm / "raw" / "round1",
        "adversarial:r1", dispatches)
    (out_arm / "detections.round1.json").write_text(json.dumps(r1_det, indent=2))
    if r1_det:
        score(corpus, r1_det, out_arm / "detections.round1.json",
              out_arm / "recall.round1.json")
    if not r1_det:
        return arm_entry(None, r1_err, len(voices), "INCOMPLETE",
                         "every round-1 voice errored; no critique possible")

    # Round 2: each voice sees the deduped, authorship-blinded union of the
    # OTHER voices' round-1 findings.
    def r2_prompt(voice: str) -> str:
        union = dedup([f for ov, fs in r1_det.items() if ov != voice for f in fs])
        prompt = critique_prompt(instructions, union)
        (out_arm / "critique").mkdir(parents=True, exist_ok=True)
        (out_arm / "critique" / f"{_fslug(voice)}.prompt").write_text(prompt)
        return prompt

    r2_det, r2_err = run_panel_round(
        dispatcher, voices, r2_prompt, out_arm / "raw" / "round2",
        "adversarial:r2", dispatches)
    total = 2 * len(voices)
    # Round-prefix the keys so both rounds' errors are counted (a voice can
    # error in either round; unprefixed keys would collide and undercount).
    errored = {f"round1:{k}": v for k, v in r1_err.items()}
    errored.update({f"round2:{k}": v for k, v in r2_err.items()})
    if not r2_det:
        return arm_entry(None, errored, total, "INCOMPLETE",
                         "every round-2 voice errored; nothing to score")
    recall, serr = score(corpus, r2_det, out_arm / "detections.json",
                         out_arm / "recall.json")
    if serr:
        return arm_entry(None, errored, total, "INCOMPLETE", serr)
    return arm_entry(recall, errored, total, "OK")


# ─────────────────────────────────────────────────────────────────────────
# Dry run
# ─────────────────────────────────────────────────────────────────────────

def dry_run(arms: list[str], voices: list[str], repeats: int,
            dispatcher: Dispatcher, ord_prompt: str, adv_prompt: str) -> int:
    def emit(arm, voice, rnd, pas, prompt):
        cmd = dispatcher.display(voice, prompt) if prompt is not None \
            else f"{dispatcher.binary()} ... <prompt:pending>"
        pc = len(prompt) if prompt is not None else "pending"
        print(f"DRY arm={arm} voice={voice} round={rnd} pass={pas} "
              f"cwd={dispatcher.cwd} prompt_chars={pc} cmd={cmd}")

    for arm in arms:
        if arm == "ordinary":
            emit(arm, voices[0], 1, 1, ord_prompt)
        elif arm == "single":
            emit(arm, voices[0], 1, 1, adv_prompt)
        elif arm == "repeated":
            for i in range(1, repeats + 1):
                emit(arm, voices[0], 1, i, adv_prompt)
        elif arm == "multi-family":
            for v in voices:
                emit(arm, v, 1, 1, adv_prompt)
        elif arm == "adversarial":
            for v in voices:
                emit(arm, v, 1, 1, adv_prompt)
            for v in voices:
                # round-2 prompt is the blinded union of others' round-1
                # findings, unknown until round 1 runs.
                emit(arm, v, 2, 1, None)
    return 0


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────

def parse_arms(raw: str) -> list[str]:
    seen, out = set(), []
    for a in (x.strip() for x in raw.split(",")):
        if not a:
            continue
        if a not in ARMS:
            sys.exit(f"error: unknown arm {a!r}; choose from {ARMS}")
        if a not in seen:
            seen.add(a)
            out.append(a)
    if not out:
        sys.exit("error: --arms selected nothing")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-registered ablation-arm runner (M3)")
    ap.add_argument("--corpus", required=True, type=Path,
                    help="seeded-defect corpus; read only by recall_score at scoring")
    ap.add_argument("--targets", required=True, type=Path,
                    help="root dir with the target crate(s) + REVIEW-INSTRUCTIONS.md")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--voices", required=True,
                    help="panel voices (csv); arm 1-3 use the first voice")
    ap.add_argument("--repeats", type=int, default=3,
                    help="passes for the repeated-same-model arm (default 3)")
    ap.add_argument("--dispatch-cmd", default=DEFAULT_DISPATCH,
                    help="command template with {model} and {prompt} placeholders")
    ap.add_argument("--per-call-timeout", type=int, default=1800)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the dispatch plan and exit without dispatching")
    args = ap.parse_args()

    arms = parse_arms(args.arms)
    voices = [v.strip() for v in args.voices.split(",") if v.strip()]
    if not voices:
        sys.exit("error: --voices selected no voices")
    if args.repeats < 1:
        sys.exit("error: --repeats must be >= 1")

    targets = args.targets.resolve()
    if not targets.is_dir():
        sys.exit(f"error: --targets is not a directory: {targets}")
    instr_path = targets / "REVIEW-INSTRUCTIONS.md"
    if not instr_path.is_file():
        sys.exit(f"error: {instr_path} not found (the target dir must carry the "
                 f"review instructions)")
    if not args.corpus.is_file():
        sys.exit(f"error: --corpus not found: {args.corpus}")
    if not RECALL_SCORE.is_file():
        sys.exit(f"error: recall_score.py missing at {RECALL_SCORE}")

    instructions = instr_path.read_text()
    contract = split_contract(instructions)
    ord_prompt = ordinary_prompt(contract)
    adv_prompt = instructions

    dispatcher = Dispatcher(args.dispatch_cmd, targets, args.per_call_timeout)

    if args.dry_run:
        return dry_run(arms, voices, args.repeats, dispatcher, ord_prompt, adv_prompt)

    if not dispatcher.available():
        log(f"INCOMPLETE: dispatch binary {dispatcher.binary()!r} not found on "
            f"PATH; no dispatch executed")
        return 3

    args.out.mkdir(parents=True, exist_ok=True)
    dispatches: list = []
    summary_arms: dict = {}
    incomplete = False

    try:
        for arm in arms:
            out_arm = args.out / arm
            out_arm.mkdir(parents=True, exist_ok=True)
            if arm == "ordinary":
                entry = run_simple_arm("ordinary", dispatcher, voices[0],
                                       ord_prompt, out_arm, args.corpus, dispatches)
            elif arm == "single":
                entry = run_simple_arm("single", dispatcher, voices[0],
                                       adv_prompt, out_arm, args.corpus, dispatches)
            elif arm == "repeated":
                entry = run_repeated_arm(dispatcher, voices[0], adv_prompt,
                                         args.repeats, out_arm, args.corpus, dispatches)
            elif arm == "multi-family":
                entry = run_multi_arm(dispatcher, voices, adv_prompt, out_arm,
                                      args.corpus, dispatches)
            else:  # adversarial
                entry = run_adversarial_arm(dispatcher, voices, instructions,
                                            out_arm, args.corpus, dispatches)
            summary_arms[arm] = entry
            if entry["status"] != "OK":
                incomplete = True
            log(f"[{arm}] {entry['status']} "
                f"({entry['successful']}/{entry['dispatches']} dispatches ok)")
    except DispatcherMissing as e:
        log(f"INCOMPLETE: dispatch binary disappeared mid-run ({e}); "
            f"no fake pass")
        return 3

    error_log = [{"arm": a, "key": k, "reason": r}
                 for a, e in summary_arms.items()
                 for k, r in e.get("errored", {}).items()]

    summary = {
        "schema": "colosseum-benchmark/v1",
        "corpus": str(args.corpus),
        "targets": str(targets),
        "dispatch_cmd": args.dispatch_cmd,
        "voices": voices,
        "repeats": args.repeats,
        "arms_requested": arms,
        "total_dispatches": len(dispatches),
        "arms": summary_arms,
        "error_log": error_log,
        "verdict": "INCOMPLETE" if incomplete else "COMPLETE",
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(f"summary: {args.out / 'summary.json'}")
    for arm in arms:
        e = summary_arms[arm]
        rec = e.get("panel_union_recall")
        rec_s = f"union_recall={rec:.2f}" if isinstance(rec, (int, float)) else "unscored"
        print(f"  {arm:<13} {e['status']:<11} {rec_s} "
              f"({e['successful']}/{e['dispatches']} ok)")
    print(f"VERDICT: {summary['verdict']}")
    return 3 if incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
