# Intent: `lru-ttl` — bounded LRU cache with TTL and generation handles

Version: 1.0. Status: implementation landed, tests deferred to the
verification stage. This document is the behavioral contract.

## Purpose

`lru-ttl` stores string entries under string keys with a per-entry TTL, a
hard capacity bound, least-recently-used eviction, and generation-stamped
handles that become invalid when the cache is cleared. An eviction callback
lets the owner observe evictions.

## Behavioral clauses

- **A1** (capacity): the number of live entries never exceeds `capacity`.
  Inserting into a full cache evicts exactly one entry first.
- **A2** (freshness): an expired entry is never returned. Every expiry
  decision consults the current time; time is read fresh for each decision,
  never reused from an earlier operation.
- **A3** (LRU order): eviction removes the least recently used entry. A
  `get` hit counts as a use. The most recently used entry is never the
  eviction victim while any other entry exists.
- **A4** (generations): `clear` advances the cache generation. A `Handle`
  issued before a `clear` MUST NOT resolve afterwards, even if the same key
  is reinserted. Handle resolution compares the handle's generation against
  the entry's generation.
- **A5** (stats): `hits` counts only lookups that returned a live value;
  `misses` counts lookups that returned nothing, including expired entries.
  `hits + misses` equals the number of `get`/`get_by_handle` calls.
- **A6** (bounded bookkeeping): internal bookkeeping structures are bounded
  by a small constant factor of `capacity`. Eviction records are drained
  during normal operation; no auxiliary structure grows without bound.
- **A7** (callback): the eviction callback receives the evicted key and
  value after the cache state is fully consistent.

## Non-goals

- Thread safety (single-threaded use; see K1).
- Persistence, weighted sizes, or per-entry callbacks.

## Trust assumptions

- K1: callers use the cache from one thread.
- K2: the time source is monotonic milliseconds.
- K3: the eviction callback does not call back into the cache.
