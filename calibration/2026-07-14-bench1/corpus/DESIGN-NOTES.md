# Corpus v2 design notes

Held-out benchmark corpus, authored 2026-07-13. Ten defects across two
targets, built to discriminate frontier voices where r1 ceilinged. r1's
defects were all local, single-file, symptom-at-cause; every frontier voice
found them. v2 defects require cross-file reasoning, spec-value knowledge,
reentrancy analysis, or noticing an enforcement that is absent rather than
wrong. Expected single-pass frontier recall: 40-70 percent.

## Defects and why each is hard

| id | anchor | category | axis | ground truth |
|---|---|---|---|---|
| AD1 | alpha/cache.rs:115 | missing-validation | spec-omission | A4's generation comparison is implemented nowhere; get_by_handle resolves on key presence alone. The `Handle::generation` and `Cache::entry_generation` accessors exist but nothing consumes them, which is the only hint. Hard because the code looks complete and the bug is an absence. |
| AD2 | alpha/clock.rs:25 | invariant-violation | cross-file + symptom-far | Clock samples time once per 8 reads; A2 forbids reusing time across decisions. Cause in clock.rs, symptom (stale expiry) surfaces in cache.rs get. A reviewer reading cache.rs sees `self.clock.now_ms()` and must follow it into clock.rs to see the reuse. |
| AD3 | alpha/evict.rs:8 | logic-inversion | cross-file | evict pops the back of `order`; cache.rs touch/insert put MRU at the back, so back is the wrong end. Requires cross-reading evict.rs against the recency discipline in cache.rs. Reading evict.rs alone, pop_back looks reasonable. |
| AD4 | alpha/evict.rs:16 | resource-leak | spec-omission | tombstones is pushed on every eviction and never drained in normal operation; compact_tombstones is public but uncalled. A6 requires bounded, drained bookkeeping. Hard because it needs a whole-lifecycle view: no single function is wrong, the drain is just missing. |
| AD5 | alpha/cache.rs:100 | invariant-violation | cross-file (method-to-method) | get records a hit before the expiry check, counting expired lookups as hits; A5 says expired lookups are misses. get_by_handle does it correctly, so a reviewer who checks one method and assumes symmetry misses it. Some voices may label this logic-inversion, which the exact-category rule counts as a miss (deliberate discrimination, mirrors r1 D6). |
| BD1 | beta/checksum.rs:5 | default-mismatch | symptom-far | CRC register initialized to 0x0000, not the spec's 0xFFFF. Encode and parse share the constant, so all local round-trips pass; only interop with a conformant peer breaks. Requires knowing CRC-16-CCITT parameters, not just reading code. |
| BD2 | beta/parse.rs:44 | missing-bounds-check | cross-file | next_frame slices payload and trailer using the claimed length without confirming the buffer holds the whole frame. A truncated frame panics. The length is validated against MAX_PAYLOAD but never against `data.len()`. |
| BD3 | beta/parse.rs:50 | error-swallowed | symptom-far | checksum mismatch returns Ok(None) instead of Err, silently dropping a corrupt frame and, inside drain, ending delivery. Looks like an ordinary need-more-data return; the harm shows up as missing frames far downstream. |
| BD4 | beta/frame.rs:11 | off-by-one | cross-file | MAX_PAYLOAD 65536 vs the spec's 65535. Admits one oversize payload. Used by both encode and parse, so the bound reads consistent internally and only mismatches the intent value. |
| BD5 | beta/parse.rs:59 | race-condition | concurrency-reentrancy | drain snapshots the byte budget before the loop; K2 permits reentrant feed, so frames fed during a callback exceed the stale budget and go undelivered, and budget can underflow. Requires reasoning about reentrant control flow, which safe Rust does not flag. |

## Hardness-axis coverage

- CROSS-FILE: AD2, AD3, AD5, BD2, BD4 (a value/discipline in one module misused or contradicted in another).
- CONCURRENCY / REENTRANCY: BD5 (stale budget under reentrant feed; a real single-thread reentrancy hazard, not memory-unsafe).
- SYMPTOM-FAR-FROM-CAUSE: AD2, BD1, BD3 (observable failure is in a different module or a different party than the root cause).
- SPEC-LEVEL OMISSION: AD1, AD4 (the intent requires enforcement no code path performs).

Every axis is covered; most defects sit on two axes.

## Distractors (correct code that looks suspicious; NOT corpus entries)

These measure false-positive pressure. A voice that flags any of them is
producing an unmatched detection, which the scorer counts but never turns
into a precision number.

1. `alpha/clock.rs remaining_ms` uses `saturating_sub` on the deadline.
   Looks like it hides an underflow; it is the intended past-due-yields-zero
   behavior.
2. `beta/checksum.rs` uses `wrapping_shl(1)`. Looks like an arithmetic
   defect; it is the correct CRC shift. The real checksum defect is the
   init value, not the shift.
3. `beta/parse.rs resync` starts scanning at index 1. Looks off-by-one; it
   correctly skips the byte already known not to start a valid magic and
   scans forward.
4. `alpha/buffer.rs`-style `consume` reset in `beta/src/buffer.rs` clears
   the whole buffer when the cursor reaches the end. Looks like it could
   drop unread bytes; it only fires when nothing is unread.

## Provenance and reuse

Held out: authored entirely under scratchpad, never committed to the
colosseum repo before the benchmark runs. Once published it is burned and
must not seed another calibration.
