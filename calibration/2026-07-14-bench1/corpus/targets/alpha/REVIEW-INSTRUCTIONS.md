# Review task

You are reviewing the `lru-ttl` crate (this repository) against its
behavioral contract, `INTENT.md`. The implementation landed recently; tests
are deferred. Your job is adversarial code review: find every place the code
violates the intent, and any defect that would matter in production even if
the intent does not name it.

Read `INTENT.md` first, then every file under `src/`. Check each clause
A1-A7 against the code that claims to implement it. Defects may span more
than one file: a value maintained in one module and misused in another, a
constant whose meaning the intent fixes, an enforcement the intent requires
that no code path performs.

## Reporting format (mandatory)

Report your findings as ONE fenced ```json code block containing a JSON
array. Each finding is an object with exactly these fields:

- `file`: repo-relative path, e.g. `"src/cache.rs"`
- `line`: integer, the line where the defect lives (the line a fix would
  change; for a missing check, the place the check belongs)
- `category`: exactly one of the taxonomy below
- `severity`: one of `"critical"`, `"high"`, `"medium"`, `"low"`
- `title`: one sentence stating the defect

Prose analysis around the block is welcome, but the block must be present,
must be valid JSON, and is the only thing that is scored.

## Category taxonomy (closed list; categorize by ROOT CAUSE)

- `off-by-one` — a boundary admits or excludes exactly one element wrongly
- `unchecked-arithmetic` — arithmetic that can wrap, overflow, or lose value
- `invariant-violation` — a stated invariant can be broken by some path
- `missing-bounds-check` — an index or range used without validation
- `default-mismatch` — a coded default differs from the documented default
- `error-swallowed` — a failure is silently absorbed instead of propagated
- `logic-inversion` — a condition or branch has inverted polarity
- `missing-validation` — an input or parameter accepted without a required check
- `race-condition` — outcome depends on unsynchronized concurrent or reentrant ordering
- `resource-leak` — memory, handles, or entries grow without bound or release
- `injection` — untrusted input reaches an interpreter or sink unescaped
- `dead-code` — code that can never execute or has no effect

Report only defects you can ground in specific lines. Do not pad the list;
a wrong finding costs credibility. There is no expected number of findings.
