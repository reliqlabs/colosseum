```json
[
  {
    "file": "src/window.rs",
    "line": 37,
    "category": "off-by-one",
    "severity": "critical",
    "title": "SlidingWindow::admit uses <= instead of <, admitting limit+1 events before denying"
  },
  {
    "file": "src/bucket.rs",
    "line": 47,
    "category": "unchecked-arithmetic",
    "severity": "high",
    "title": "ticks * refill_rate multiplies u32 values that can overflow before clamping"
  },
  {
    "file": "src/bucket.rs",
    "line": 48,
    "category": "unchecked-arithmetic",
    "severity": "high",
    "title": "tokens + owed adds u32 values that can overflow before min(capacity)"
  },
  {
    "file": "src/bucket.rs",
    "line": 65,
    "category": "invariant-violation",
    "severity": "high",
    "title": "deposit uses saturating_add to u32::MAX instead of clamping to capacity"
  },
  {
    "file": "src/api.rs",
    "line": 70,
    "category": "missing-bounds-check",
    "severity": "high",
    "title": "stats_for indexes shards without validation, panicking on out-of-range instead of returning None"
  },
  {
    "file": "src/config.rs",
    "line": 9,
    "category": "default-mismatch",
    "severity": "medium",
    "title": "DEFAULT_BURST is 80 but INTENT B5 requires the default burst to be 8"
  },
  {
    "file": "src/config.rs",
    "line": 67,
    "category": "error-swallowed",
    "severity": "high",
    "title": "rate parse failure silently falls back to DEFAULT_RATE instead of returning ConfigError::Malformed"
  },
  {
    "file": "src/api.rs",
    "line": 46,
    "category": "logic-inversion",
    "severity": "critical",
    "title": "allowlist check is inverted: allowlisted keys are rate-limited and non-allowlisted keys bypass entirely"
  },
  {
    "file": "src/bucket.rs",
    "line": 25,
    "category": "missing-validation",
    "severity": "critical",
    "title": "TokenBucket::new does not reject zero refill_interval_ms, causing division by zero in refill"
  }
]
```
