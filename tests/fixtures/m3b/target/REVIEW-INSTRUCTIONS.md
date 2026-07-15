# Review task

You are reviewing this crate against its behavioral contract, `INTENT.md`.
Your job is adversarial code review: find every place the code violates the
intent, and any defect that would matter in production.

Read `INTENT.md` first, then every file under `src/`.

## Reporting format (mandatory)

Report your findings as ONE fenced ```json code block containing a JSON array.
Each finding is an object with exactly these fields:

- `file`: repo-relative path, e.g. `"src/a.rs"`
- `line`: integer, the line where the defect lives
- `category`: exactly one of the taxonomy below
- `severity`: one of `"critical"`, `"high"`, `"medium"`, `"low"`
- `title`: one sentence stating the defect

The block must be present, valid JSON, and is the only thing that is scored.

## Category taxonomy (closed list)

- `off-by-one`
- `unchecked-arithmetic`
- `invariant-violation`
- `missing-bounds-check`
- `default-mismatch`
- `error-swallowed`
