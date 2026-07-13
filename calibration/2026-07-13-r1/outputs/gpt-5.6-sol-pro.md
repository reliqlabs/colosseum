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
    "file": "src/bucket.rs",
    "line": 25,
    "category": "missing-validation",
    "severity": "high",
    "title": "TokenBucket::new accepts a zero refill interval, causing refill to divide by zero."
  },
  {
    "file": "src/bucket.rs",
    "line": 43,
    "category": "unchecked-arithmetic",
    "severity": "high",
    "title": "Casting the u64 tick count to u32 truncates large elapsed intervals instead of saturating."
  },
  {
    "file": "src/bucket.rs",
    "line": 47,
    "category": "unchecked-arithmetic",
    "severity": "high",
    "title": "Multiplying the tick count by the refill rate can overflow before tokens are clamped."
  },
  {
    "file": "src/bucket.rs",
    "line": 48,
    "category": "unchecked-arithmetic",
    "severity": "high",
    "title": "Adding owed tokens can overflow before the capacity clamp is applied."
  },
  {
    "file": "src/bucket.rs",
    "line": 65,
    "category": "invariant-violation",
    "severity": "high",
    "title": "deposit saturates at u32::MAX rather than capacity, allowing the token count to exceed capacity."
  },
  {
    "file": "src/config.rs",
    "line": 9,
    "category": "default-mismatch",
    "severity": "high",
    "title": "The default burst is 80 instead of the required value 8."
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
    "title": "The allowlist condition is inverted, so allowlisted keys are throttled while every other key bypasses limiting."
  },
  {
    "file": "src/api.rs",
    "line": 52,
    "category": "unchecked-arithmetic",
    "severity": "medium",
    "title": "Deriving the sliding-window duration by multiplying interval_ms by 10 can overflow."
  },
  {
    "file": "src/api.rs",
    "line": 58,
    "category": "unchecked-arithmetic",
    "severity": "medium",
    "title": "The admitted request counter can overflow in a long-running limiter."
  },
  {
    "file": "src/api.rs",
    "line": 60,
    "category": "unchecked-arithmetic",
    "severity": "medium",
    "title": "The denied request counter can overflow in a long-running limiter."
  },
  {
    "file": "src/api.rs",
    "line": 70,
    "category": "missing-bounds-check",
    "severity": "high",
    "title": "stats_for indexes the shard vector without validation and panics for an out-of-range shard."
  }
]
```
