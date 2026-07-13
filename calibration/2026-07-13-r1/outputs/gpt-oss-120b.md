```json
[
  {
    "file": "src/window.rs",
    "line": 37,
    "category": "off-by-one",
    "severity": "critical",
    "title": "SlidingWindow admits one extra event beyond the configured limit"
  },
  {
    "file": "src/bucket.rs",
    "line": 48,
    "category": "unchecked-arithmetic",
    "severity": "high",
    "title": "TokenBucket::refill adds tokens with unchecked overflow, violating saturation guarantee"
  },
  {
    "file": "src/bucket.rs",
    "line": 65,
    "category": "invariant-violation",
    "severity": "high",
    "title": "TokenBucket::deposit can raise token count above capacity, breaking the capacity invariant"
  },
  {
    "file": "src/api.rs",
    "line": 70,
    "category": "missing-bounds-check",
    "severity": "critical",
    "title": "Limiter::stats_for indexes shards without range validation, may panic on out‑of‑range shard"
  },
  {
    "file": "src/config.rs",
    "line": 9,
    "category": "default-mismatch",
    "severity": "critical",
    "title": "DEFAULT_BURST is set to 80, contradicting intent default burst of 8"
  },
  {
    "file": "src/config.rs",
    "line": 67,
    "category": "error-swallowed",
    "severity": "high",
    "title": "Config::parse silently substitutes DEFAULT_RATE on malformed rate value instead of returning an error"
  },
  {
    "file": "src/api.rs",
    "line": 46,
    "category": "logic-inversion",
    "severity": "critical",
    "title": "Limiter::check inverts allowlist logic, limiting allowlisted keys and always admitting others"
  },
  {
    "file": "src/bucket.rs",
    "line": 24,
    "category": "missing-validation",
    "severity": "critical",
    "title": "TokenBucket::new does not reject a zero refill_interval_ms, violating B8 validation requirement"
  }
]
```
