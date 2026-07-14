# Intent: `framer` — chunked wire-protocol framer with checksums

Version: 1.0. Status: implementation landed, tests deferred to the
verification stage. This document is the behavioral contract.

## Purpose

`framer` encodes payloads into checksummed frames and incrementally parses
frames out of a byte stream that arrives in arbitrary chunks. Wire format,
big-endian:

```
MAGIC (0xA5 0x5A) | len: u32 | payload (len bytes) | crc16: u16
```

## Behavioral clauses

- **P1** (checksum): the trailer is CRC-16-CCITT, polynomial 0x1021,
  initial value 0xFFFF, computed over the payload. Encode writes it; parse
  verifies it before delivering a payload. This exact parameterization is
  the interoperability contract (K3).
- **P2** (bounds): payload length is at most 65535 bytes. Both encode and
  parse enforce the bound; parse validates the length field against the
  buffered data before any slicing or offset movement.
- **P3** (backpressure): unconsumed buffered bytes never exceed
  `HIGH_WATER` (1 MiB). A `feed` that would exceed it is rejected with
  `FrameError::Backpressure` and buffers nothing.
- **P4** (malformed frames): a frame failing magic or checksum verification
  surfaces `FrameError` to the caller, and parsing resynchronizes at the
  next magic sequence. Malformed input is never silently dropped.
- **P5** (arithmetic): offset and length arithmetic never wraps. Additions
  over attacker-influenced values are checked or bounded before use.
- **P6** (partial frames): the bytes of an incomplete trailing frame are
  preserved intact across `feed`, `drain`, and internal compaction.

## Non-goals

- Thread safety (single-threaded use; K1).
- Flow control beyond the single HIGH_WATER bound; encryption; versioning.

## Trust assumptions

- K1: callers use the framer from one thread.
- K2: the frame handler passed to `drain` MAY call `feed` on the same
  framer; reentrant feeding is a supported pattern.
- K3: peer implementations follow this specification exactly.
