```json
[
  {
    "file": "src/api.rs",
    "line": 46,
    "category": "logic-inversion",
    "severity": "critical",
    "title": "B7 inverted: allowlisted keys are rate-limited while all non-allowlisted keys bypass enforcement via the else branch returning Ok(true)."
  },
  {
    "file": "src/window.rs",
    "line": 37,
    "category": "off-by-one",
    "severity": "high",
    "title": "B1 off-by-one: `events.len() <= self.limit` admits the limit+1-th event instead of denying it; should be `<`."
  },
  {
    "file": "src/config.rs",
    "line": 9,
    "category": "default-mismatch",
    "severity": "high",
    "title": "B5 default-mismatch: DEFAULT_BURST is 80 but the intent specifies a default burst of 8."
  },
  {
    "file": "src/config.rs",
    "line": 67,
    "category": "error-swallowed",
    "severity": "high",
    "title": "B6 violated: a malformed `rate` value is silently replaced with DEFAULT_RATE via unwrap_or instead of being rejected as ConfigError::Malformed."
  },
  {
    "file": "src/bucket.rs",
    "line": 25,
    "category": "missing-validation",
    "severity": "high",
    "title": "B8 violated: TokenBucket::new never checks for zero refill_interval_ms, so refill later divides by zero (panic) and ConfigError::ZeroInterval is unreachable."
  },
  {
    "file": "src/bucket.rs",
    "line": 47,
    "category": "unchecked-arithmetic",
    "severity": "high",
    "title": "B2 violated: `ticks * self.refill_rate` is an unchecked u32 multiply that can overflow (panic in debug, wrap in release)."
  },
  {
    "file": "src/bucket.rs",
    "line": 48,
    "category": "unchecked-arithmetic",
    "severity": "medium",
    "title": "B2 violated: `self.tokens + owed` can overflow u32 before the `.min(capacity)` clamp is applied; addition must saturate."
  },
  {
    "file": "src/bucket.rs",
    "line": 65,
    "category": "invariant-violation",
    "severity": "high",
    "title": "B3 violated: deposit saturating_adds tokens without clamping to capacity, allowing token count to exceed capacity."
  },
  {
    "file": "src/api.rs",
    "line": 70,
    "category": "missing-bounds-check",
    "severity": "high",
    "title": "B4 violated: stats_for indexes self.shards[shard] directly, panicking on an out-of-range shard instead of returning None."
  },
  {
    "file": "src/bucket.rs",
    "line": 43,
    "category": "unchecked-arithmetic",
    "severity": "low",
    "title": "B2 violated: `(elapsed / self.refill_interval_ms) as u32` truncates for large elapsed time, silently losing tick value instead of saturating."
  },
  {
    "file": "src/api.rs",
    "line": 48,
    "category": "resource-leak",
    "severity": "medium",
    "title": "The keys HashMap inserts a KeyState per distinct key with no eviction, growing without bound under many caller-supplied keys."
  }
]
```
