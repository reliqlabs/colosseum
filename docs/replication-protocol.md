# Independent replication protocol (M6)

This is the gate for the word "validated" returning to the README (see
[ROADMAP.md](../ROADMAP.md#w4-m6-independent-replication-owner-user-external-party)).
It tells an independent party exactly what to run and what to send back, so
their run is comparable and citable against this repo's own claims.

Read [README.md](../README.md), [QUICKSTART.md](../QUICKSTART.md), and
[INSTALL.md](../INSTALL.md) first if you have not set up a Colosseum project
before. This document assumes you can already install and run the repo; it
adds the specific sequence that counts as a replication and the bundle that
makes it checkable.

## 1. What replication means here

Independent execution of the workflow on your own machine, by someone with
no commit history in this repo, producing your own evidence trail: your own
`colosseum_doctor` output, your own `ci.py` run, your own `r22` run, your
own hashes.

Two things this is explicitly not:

- **Not an endorsement.** A replication reports what happened on your
  machine, under your toolchain versions, at the commit you checked out. It
  is evidence, not a stamp of approval.
- **Not required to succeed.** A failed replication — a gate that did not
  pass on your machine, a mismatch against this repo's own results — is a
  first-class result. Report it with the same bundle and the same rigor as
  a clean pass. Do not fix, retry-until-green, or omit a failing run before
  submitting; per [dogfood-evidence.md](./dogfood-evidence.md), honest
  negative or incomplete evidence is the required shape, not a defect in
  your work.

## 2. Environment

1. Follow [INSTALL.md](../INSTALL.md). At minimum you need §1.1 (Rust),
   §1.2 (Python 3.11+ and `uv`), §1.3 (JVM 17+, needed by Apalache, which
   `quint verify` invokes), §2 (clone), and §3.1 (Quint). Add §7 (OpenCode
   CLI + providers) only if you intend to run the optional extended half in
   step 3(c).
2. From the repo root, run the preflight diagnostic and capture its output:

   ```bash
   ./scripts/colosseum_doctor.py --json > doctor.json
   cat doctor.json
   ```

   `colosseum_doctor.py` compares your installed tool versions against
   [`bom.json`](../bom.json), checks the voice registry, and (with
   `--project`) diffs a project's dispatch scripts against the repo's
   canonical copies. You do not need `--project` for this replication — you
   are running against the repo itself, not a downstream project. Include
   `doctor.json` verbatim in your return bundle (section 4).
3. Minimum toolchain for a meaningful replication: `cargo` and `quint` on
   `PATH`. `quint verify` auto-downloads Apalache to `~/.quint/apalache`
   (~250 MB) on first invocation; pre-warm it once outside automation
   (`quint verify --max-steps=1 <any>.qnt`) before step 3. Without `cargo`
   or `quint`, `tests/r22_reference_project.py` exits 2 (SKIP-FAIL) and the
   replication cannot proceed past this step — report that outcome rather
   than stopping silently.
4. Kani and Lean are optional tiers. Neither is required by the two
   mandatory runs in step 3: `tests/r22_reference_project.py` drives
   `pyramid_run.py --profile tested`, which does not include Kani or Lean
   (those enter at the `bounded` and `proved` profiles). If you have Kani
   installed, you may additionally run
   `./scripts/pyramid_run.py --crate tests/fixtures/r22/project --profile bounded`
   against the reference project as an enrichment; if you have Lean
   installed, `--profile proved` includes Verus and Lean, but note the Lean
   layer under a headless run always reports `not_run`/INCOMPLETE by
   design (`scripts/pyramid_run.py`) regardless of whether Lean is
   installed — that is expected, not a broken install. When a tool is
   absent, record the resulting INCOMPLETE as a result and move on; per
   this repo's own convention (`tests/README.md`, `docs/self-measurement.md`),
   INCOMPLETE is not a failure of the replication, it is what an honest
   partial-toolchain run reports.

## 3. The replication runs, in order

Run all commands from the repo root, on a clean checkout, and record the
exact commit (`git rev-parse HEAD`) and whether the tree was dirty
(`git status --porcelain`) before you start.

**(a) The repo's own gates:**

```bash
./scripts/ci.py 2>&1 | tee ci-output.txt
echo "ci.py exit=$?" >> ci-output.txt
```

Runs frontmatter validation, agent-lint, roster-drift, doc-links,
dispatch-config, and the full regression suite (`tests/run_all.py`, ~24
suites — this already includes `r22_reference_project.py` as one of the
`tests/r*.py` suites it globs). Exit 0 pass, 1 a check failed, 2 usage
error. Use `--strict` if you want an INCOMPLETE regression suite (a
toolchain-absent suite) to also fail the run; report whichever mode you
used.

**(b) The end-to-end reference project, standalone:**

```bash
./tests/r22_reference_project.py 2>&1 | tee r22-output.txt
echo "r22 exit=$?" >> r22-output.txt
```

This duplicates part of what `ci.py`'s regression step already ran in (a);
run it again standalone anyway; `ci.py`'s output aggregates ~24 suites
together and `r22`'s per-check detail (the known-good `jobq` project
passing every gate, six known-bad mutations each failing at exactly their
intended gate) is worth having as its own legible artifact. Exit 0 pass, 1
fail, 2 toolchain unavailable (SKIP-FAIL).

**(c) OPTIONAL — extended half: a fresh adversarial panel run.**

A panel attack on the r22 project's intent has not yet been run by this
repo's own maintainers (see ROADMAP.md's exit-criterion-7 note); running it
independently is valuable data even though it is optional here. Copy the
fixture out of the tracked tree first so your run's artifacts do not land
inside `tests/fixtures/`:

```bash
mkdir -p /tmp/r22-panel && cp -R tests/fixtures/r22/project /tmp/r22-panel/
```

Then follow [`skills/colosseum-adversarial/SKILL.md`](../skills/colosseum-adversarial/SKILL.md)
and [`scripts/opencode_dispatch.py`](../scripts/opencode_dispatch.py) against
`/tmp/r22-panel/project/INTENT.md` as `TARGET_SPEC`, using whatever voices
you have credentials for. Your voice roster will differ from the canonical
panel pinned in `registry/voices.json` — that is fine and expected. Record
it, do not hide it: name each voice's exact provider/model id, and do not
describe your roster as "the canonical panel" unless it is byte-identical
to the pin recorded in `registry/voices.json` at your checkout commit.

## 4. The return bundle

Collect these into one directory before hashing:

- `doctor.json` (step 2.2)
- `ci-output.txt` (step 3a), including its exit code
- `r22-output.txt` (step 3b), including its exit code
- a `versions.txt` note: your checkout commit, dirty-tree status, and
  `bom.json` at that commit vs. what `doctor.json` reported you actually
  had installed (`doctor.json`'s own toolchain-vs-BOM comparison already
  carries this; `versions.txt` is a one-line human summary pointing at it)
- panel outputs from step 3c, if you ran it, under `.colosseum/attacks/`
  as written by the dispatch tooling — verbatim, unedited
- a short prose report of divergences: anything that passed here and would
  not on the authoring machine, anything that failed here and passed there,
  any INCOMPLETE result and why, any tool version that differed from
  `bom.json`'s pin
- a `sha256-manifest.txt` covering every file above, so the bundle is
  tamper-evident once merged:

  ```bash
  # from inside the bundle directory
  find . -type f ! -name sha256-manifest.txt -print0 \
    | xargs -0 shasum -a 256 | sort -k2 > sha256-manifest.txt
  # Linux: substitute `sha256sum` for `shasum -a 256`
  ```

## 5. How results are recorded

Open a PR against this repo adding a `replications/<ISO-date>-<party>/`
directory containing the bundle from section 4, plus a manifest file at
`replications/<ISO-date>-<party>/manifest.json` following the
`colosseum-dogfood-evidence/v1` conventions in
[dogfood-evidence.md](./dogfood-evidence.md): a `status` field of
`observation` or `manifested`, honest `null`s wherever a value was not
captured rather than a plausible-looking guess, and the same field
discipline (commit, hashes, tool/model versions, bounds, seeds,
raw-report hashes) scoped to this replication run instead of a dogfood
project. Minimum manifest shape:

```json
{
  "schema": "colosseum-replication-manifest/v1",
  "status": "observation",
  "party": "<name or handle>",
  "generated_at": "<ISO-8601 UTC>",
  "repo_commit": "<git rev-parse HEAD>",
  "dirty_tree": false,
  "bundle_sha256_manifest": "sha256-manifest.txt",
  "ci_py": { "exit_code": 0, "output": "ci-output.txt" },
  "r22": { "exit_code": 0, "output": "r22-output.txt" },
  "extended_panel_run": false,
  "divergences_from_authoring_run": "<prose, or null if none observed>",
  "notes": "<free-form provenance notes>"
}
```

Use `status: manifested` only once every field above carries a real,
verifiable value (no unrecorded commit, no unrecorded hash). An
`observation`-status replication is still mergeable and still counts as a
first-class result; it is just labeled honestly.

The word "validated" returns to the README only after both hold, per
ROADMAP's [W4](../ROADMAP.md#w4-m6-independent-replication-owner-user-external-party)
and [exit criterion 10](../ROADMAP.md#exit-criteria-scoreboard): at least
one independent replication directory of this shape is merged, **and**
[the pre-registered benchmark](./benchmark-protocol.md) has published
results (positive or negative — see its own
[negative-results commitment](./benchmark-protocol.md#negative-results-commitment)).
One without the other is not enough.

## 6. Corpus authorship offer

The strongest replication also authors a held-out seeded-defect corpus for
[the M3 benchmark](./benchmark-protocol.md#seeded-defect-corpus). The
existing calibration corpus is burned (published, and too easy — most
voices ceilinged at 8/8; see `calibration/2026-07-13-r1/README.md`). A
corpus authored by a party outside this repo closes the
orchestrator-blindness gap noted in
[ROADMAP's W2](../ROADMAP.md#w2-m3-prospective-benchmark-owner-maintaineragent-api-cost):
the person planting defects is not the person who has been staring at this
methodology's own blind spots. If you want to take this on, follow the
schema in
[`templates/seeded-defect-corpus.example.json`](../templates/seeded-defect-corpus.example.json)
and coordinate with the maintainer before publishing it anywhere the panel
voices could see it pre-run — a leaked corpus burns itself the same way the
first one did.
