Every behavioral clause B1–B8 is violated or undermined by the code. Findings, with the scored JSON block at the end:

- **B1** (`api.rs`): offset assignment reads `next_offset()` under a read lock, drops it, and only later takes the write lock to insert. Two concurrent appends both read offset N, both write records at N, and the second index insert overwrites the first. Additionally, rotation at line 69 happens after the record is already committed, so a `Segment::new` failure there returns an error for a write that took effect and wedges the ledger.
- **B2** (`api.rs:40,43`): `open` checks `checkpoint_threshold` instead of `max_records_per_segment`, then clamps zero capacity to 1 with `.max(1)` instead of returning `ZeroSegmentCapacity`.
- **B3** (`segment.rs:48`): seal condition is `len() > max_records`, evaluated after the push, so every segment holds `max_records + 1` records before sealing.
- **B4** (`replay.rs:30`): decode failures are silently skipped (`if let Ok(...)`), replay continues past the corrupt record, and `Ok` is returned. Exactly the silent divergence the clause forbids.
- **B5** (`checkpoint.rs:26`): `retention_watermark` is discarded; `capture` can record a `last_applied` below the watermark.
- **B6** (`checkpoint.rs:34`): `pending < threshold` is inverted; a checkpoint is "due" when too few records are pending and not due when the threshold is met.
- **B7** (`index.rs:58`): `prune_before` is a no-op; the index grows without bound.
- **B8** (`index.rs:50`): `relative_position` uses raw subtraction, which underflows/wraps when `absolute < base_offset` and never rejects an offset outside the segment.
- Cross-cutting (`segment.rs:67`): `prune_before` retains a suffix without advancing `base_offset`, so positional reads via `get_relative`/`read_at` mis-index: retained records read as `NotFound` and reclaimed offsets alias onto live records' payloads.

```json
[
  {
    "file": "src/api.rs",
    "line": 40,
    "category": "missing-validation",
    "severity": "high",
    "title": "open() validates checkpoint_threshold instead of max_records_per_segment, so zero segment capacity is accepted and threshold==0 is wrongly rejected with ZeroSegmentCapacity, violating B2."
  },
  {
    "file": "src/api.rs",
    "line": 43,
    "category": "error-swallowed",
    "severity": "high",
    "title": "open() clamps max_records_per_segment to 1 with .max(1) instead of propagating ZeroSegmentCapacity, silently rewriting an invalid config the contract requires to be rejected."
  },
  {
    "file": "src/api.rs",
    "line": 58,
    "category": "race-condition",
    "severity": "critical",
    "title": "append() reads next_offset() under a released read lock and inserts under a later write lock, so concurrent appends receive duplicate offsets and index entries overwrite each other, violating B1."
  },
  {
    "file": "src/api.rs",
    "line": 69,
    "category": "invariant-violation",
    "severity": "high",
    "title": "append() creates the rotation segment with the unvalidated config capacity after the record is already pushed, so a Segment::new failure returns an error for a committed write, leaves the offset unindexed and reusable, and wedges all future appends behind Sealed."
  },
  {
    "file": "src/segment.rs",
    "line": 48,
    "category": "off-by-one",
    "severity": "high",
    "title": "push() seals only when records.len() > max_records after pushing, so every segment admits max_records + 1 records before sealing, violating B3 (condition must be >=)."
  },
  {
    "file": "src/segment.rs",
    "line": 67,
    "category": "invariant-violation",
    "severity": "critical",
    "title": "prune_before() retains a suffix without advancing base_offset, breaking the offset-minus-base position invariant so get_relative/read_at return NotFound for live records and return a live record's payload for reclaimed offsets."
  },
  {
    "file": "src/index.rs",
    "line": 50,
    "category": "unchecked-arithmetic",
    "severity": "high",
    "title": "relative_position() computes absolute - seg.base_offset with raw subtraction that panics or wraps when absolute < base_offset and never rejects offsets outside the segment, violating B8."
  },
  {
    "file": "src/index.rs",
    "line": 58,
    "category": "resource-leak",
    "severity": "high",
    "title": "OffsetIndex::prune_before() discards its watermark and drops nothing, so index entries for reclaimed records are retained forever and the index grows without bound, violating B7."
  },
  {
    "file": "src/replay.rs",
    "line": 30,
    "category": "error-swallowed",
    "severity": "critical",
    "title": "replay_from() skips records that fail decode via if let Ok(...) and still returns Ok, silently applying a diverged prefix/suffix instead of aborting with Corrupt, violating B4."
  },
  {
    "file": "src/checkpoint.rs",
    "line": 26,
    "category": "missing-validation",
    "severity": "high",
    "title": "Checkpoint::capture() ignores retention_watermark, so a captured checkpoint can name a last_applied offset that retention is permitted to reclaim, violating B5."
  },
  {
    "file": "src/checkpoint.rs",
    "line": 34,
    "category": "logic-inversion",
    "severity": "high",
    "title": "should_checkpoint() returns pending < threshold, reporting a checkpoint due when too few records are pending and none due once threshold is reached, the exact inverse of B6."
  }
]
```
