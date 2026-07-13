```json
[
  {
    "file": "src/window.rs",
    "line": 37,
    "category": "off-by-one",
    "severity": "high",
    "title": "The sliding window admits limit+1 events because it accepts when occupancy equals the limit."
  },
  {
    "file": "src/config.rs",
    "line": 9,
    "category": "default-mismatch",
    "severity": "medium",
    "title": "The default burst capacity is 80 instead of the required 8."
  },
  {
    "file": "src/config.rs",
    "line": 67,
    "category": "error-swallowed",
    "severity": "high",
    "title": "An invalid rate value is silently replaced with the default instead of returning ConfigError::Malformed."
  },
  {
    "file": "src/api.rs",
    "line": 46,
    "category": "logic-inversion",
    "severity": "critical",
    "title": "Allowlisted keys are rate limited while every non-allowlisted key is admitted unconditionally."
  },
  {
    "file": "src/api.rs",
    "line": 70,
    "category": "missing-bounds-check",
    "severity": "high",
    "title": "stats_for indexes the shard vector without validation and panics for out-of-range indices."
  },
  {
    "file": "src/bucket.rs",
    "line": 25,
    "category": "missing-validation",
    "severity": "critical",
    "title": "TokenBucket::new accepts a zero refill interval, causing refill to divide by zero."
  },
  {
    "file": "src/bucket.rs",
    "line": 43,
    "category": "unchecked-arithmetic",
    "severity": "high",
    "title": "Casting the elapsed tick count from u64 to u32 truncates large elapsed intervals instead of saturating."
  },
  {
    "file": "src/bucket.rs",
    "line": 47,
    "category": "unchecked-arithmetic",
    "severity": "high",
    "title": "Multiplying the tick count by the refill rate can overflow instead of saturating."
  },
  {
    "file": "src/bucket.rs",
    "line": 48,
    "category": "unchecked-arithmetic",
    "severity": "high",
    "title": "Adding owed tokens to the current token count can overflow before the capacity clamp executes."
  },
  {
    "file": "src/bucket.rs",
    "line": 65,
    "category": "invariant-violation",
    "severity": "high",
    "title": "deposit saturates only at u32::MAX and can raise the token count above bucket capacity."
  },
  {
    "file": "src/api.rs",
    "line": 52,
    "category": "unchecked-arithmetic",
    "severity": "high",
    "title": "Constructing a per-key window multiplies interval_ms by 10 without overflow protection."
  },
  {
    "file": "src/api.rs",
    "line": 58,
    "category": "unchecked-arithmetic",
    "severity": "low",
    "title": "Shard admission and denial counters can overflow in a long-running process."
  }
]
```
