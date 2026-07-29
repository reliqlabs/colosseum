# Intent: `throttle` — per-key request rate limiter

Version: 1.0. Status: implementation landed, tests deferred to the verification
stage. This document is the behavioral contract the implementation must satisfy.

## Purpose

`throttle` decides, per caller-supplied key, whether a request is admitted.
Two mechanisms compose: a token bucket (sustained rate + burst) and a sliding
window (hard cap per interval). A request is admitted only if both agree.

## Behavioral clauses

- **B1** (window cap): `SlidingWindow::admit` permits at most `limit` events
  per window. The `limit+1`-th event whose timestamp falls inside the current
  window MUST be denied.
- **B2** (saturating refill): token refill arithmetic MUST saturate. Token
  counts never wrap, overflow, or go negative, for any elapsed time and any
  configured rate.
- **B3** (capacity invariant): at every observable point, a bucket's token
  count is `<= capacity`. Every path that adds tokens MUST clamp to capacity.
- **B4** (shard bounds): `Limiter::stats_for(shard)` MUST validate the shard
  index and return `None` for an out-of-range index. It never panics.
- **B5** (burst default): when a config omits `burst`, the default is **8**.
- **B6** (strict config): a malformed config line MUST be rejected with
  `ConfigError::Malformed`. No field is ever silently replaced with a default
  because it failed to parse.
- **B7** (allowlist): keys on the allowlist BYPASS rate limiting entirely.
  All keys not on the allowlist are enforced normally.
- **B8** (constructor validation): `TokenBucket::new` MUST reject a zero
  `refill_interval_ms` with `ConfigError::ZeroInterval`. No later operation
  may divide by a caller-supplied zero.

## Non-goals

- Distributed coordination across processes (single-process only).
- Persistence of limiter state across restarts.
- Sub-millisecond timing precision.

## Trust assumptions

- K1: callers supply monotonically non-decreasing timestamps (`now_ms`).
- K2: config text is operator-authored, not attacker-controlled.
