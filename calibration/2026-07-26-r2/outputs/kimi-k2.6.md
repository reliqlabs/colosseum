The `ledger` crate violates its behavioral contract in multiple places. The most severe issues are a race condition that breaks offset uniqueness (B1), a replay implementation that silently skips corruption (B4), and an open-time validation that checks the wrong configuration field (B2). Several clauses (B5–B8) are either unimplemented or implemented with arithmetic that can underflow.

```json
[
  {
    "file": "src/api.rs",
    "line": 40,
    "category": "missing-validation",
    "severity": "critical",
    "title": "open checks checkpoint_threshold instead of max_records_per_segment, and .max(1) silently masks zero segment capacity, violating B2"
  },
  {
    "file": "src/api.rs",
    "line": 56,
    "category": "race-condition",
    "severity": "critical",
    "title": "append computes offset outside the segments lock, allowing concurrent threads to append the same offset, violating B1 uniqueness"
  },
  {
    "file": "src/segment.rs",
    "line": 48,
    "category": "off-by-one",
    "severity": "high",
    "title": "push seals after the record is added, allowing max_records+1 records per segment, violating B3"
  },
  {
    "file": "src/replay.rs",
    "line": 30,
    "category": "error-swallowed",
    "severity": "critical",
    "title": "replay silently skips corrupt records with if-let instead of aborting, violating B4 all-or-nothing semantics"
  },
  {
    "file": "src/checkpoint.rs",
    "line": 20,
    "category": "invariant-violation",
    "severity": "high",
    "title": "capture ignores retention_watermark, allowing a checkpoint below the watermark, violating B5"
  },
  {
    "file": "src/checkpoint.rs",
    "line": 34,
    "category": "logic-inversion",
    "severity": "high",
    "title": "should_checkpoint returns pending < threshold instead of pending >= threshold, inverting B6 cadence"
  },
  {
    "file": "src/index.rs",
    "line": 58,
    "category": "invariant-violation",
    "severity": "high",
    "title": "prune_before is a no-op, leaving reclaimed offsets in the index, violating B7"
  },
  {
    "file": "src/index.rs",
    "line": 50,
    "category": "unchecked-arithmetic",
    "severity": "medium",
    "title": "relative_position subtracts seg.base_offset without checking absolute >= base, allowing underflow, violating B8"
  },
  {
    "file": "src/segment.rs",
    "line": 62,
    "category": "invariant-violation",
    "severity": "high",
    "title": "prune_before removes records without updating base_offset, breaking relative reads for retained records"
  },
  {
    "file": "src/api.rs",
    "line": 69,
    "category": "unchecked-arithmetic",
    "severity": "medium",
    "title": "Segment rotation uses offset + 1 without checked addition, allowing u64 wrap"
  },
  {
    "file": "src/checkpoint.rs",
    "line": 24,
    "category": "unchecked-arithmetic",
    "severity": "medium",
    "title": "capture computes index.next_offset() - 1 without checking next_offset > 0, allowing underflow"
  },
  {
    "file": "src/segment.rs",
    "line": 56,
    "category": "unchecked-arithmetic",
    "severity": "medium",
    "title": "get_relative casts u64 to usize without bounds check, truncating on 32-bit platforms"
  }
]
```
