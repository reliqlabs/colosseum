# INTENT: `ledger`

An append-only, segmented event log with an in-memory offset index, periodic
checkpointing, and crash replay. This document is the behavioral contract the
implementation must satisfy. Clauses are normative.

## 1. Purpose

A process appends opaque payloads to a durable log. Each append returns an
offset. Records are grouped into fixed-size segments so old data can be
reclaimed. A checkpoint records how far a consumer has applied the log; after
a crash the consumer replays only the records after the checkpoint.

## 2. Data model

- **Offset** — a `u64` naming one record. Offsets are assigned by the ledger.
- **Segment** — a contiguous run of records beginning at `base_offset`. A
  segment is *sealed* when full; sealed segments never accept writes.
- **Index** — maps an offset to the segment holding it.
- **Checkpoint** — `(last_applied, segment_base)`. Replay resumes at
  `last_applied + 1`.
- **Retention watermark** — the offset below which records may be reclaimed.

## 3. Behavioral clauses

**B1 — offsets are unique and dense.** Every successful append returns an
offset exactly one greater than the previous successful append, starting at 0.
This holds under concurrent appends from multiple threads: no two appends may
observe or return the same offset, and no offset may be skipped.

**B2 — zero segment capacity is rejected.** Opening a ledger whose
per-segment record capacity is zero fails with `ZeroSegmentCapacity`. A
zero-capacity segment would seal on every append and make offset assignment
degenerate, so the check belongs at open time, on the capacity field itself.

**B3 — segments respect their capacity.** No segment ever holds more than
`max_records` records. A segment reaching capacity is sealed, and the next
append goes to a fresh segment.

**B4 — replay is all-or-nothing on corruption.** If a record in the replay
range fails to decode, replay aborts and reports `Corrupt` with that record's
offset. Replay never skips an undecodable record and reports success: a
consumer that applied a prefix of the log while believing it applied all of it
is silently diverged.

**B5 — a checkpoint is always replayable.** A captured checkpoint must never
name an offset that retention is permitted to reclaim. `last_applied` must sit
at or above the retention watermark, so the segment it names is guaranteed to
still exist when replay reads it.

**B6 — checkpoint cadence.** A checkpoint is due once at least `threshold`
records are pending. Fewer than `threshold` pending records means no
checkpoint is due.

**B7 — retention reclaims index entries.** After a retention pass drops
records below the watermark, the index must not retain entries naming those
records. The index may not grow without bound as records are reclaimed.

**B8 — offset arithmetic is total.** Converting an absolute offset to a
position within a segment must not wrap or underflow. If the absolute offset
does not belong to the given segment, the conversion must reject it rather
than produce a position.

## 4. Out of scope

Durability to disk, encryption, compaction, and multi-writer coordination
across processes. Tests are deferred; this contract and `src/` are what exist.
