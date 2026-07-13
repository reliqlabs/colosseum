[
  {
    "file": "src/window.rs",
    "line": 37,
    "category": "off-by-one",
    "severity": "critical",
    "title": "SlidingWindow::admit allows limit+1 events instead of limit"
  },
  {
    "file": "src/bucket.rs",
    "line": 47,
    "category": "unchecked-arithmetic",
    "severity": "serious",
    "title": "Token refill multiplication can overflow"
  },
  {
    "file": "src/bucket.rs",
    "line": 65,
    "category": "invariant-violation",
    "severity": "serious",
    "title": "deposit method doesn't clamp token count to capacity"
  },
  {
    "file": "src/api.rs",
    "line": 70,
    "category": "missing-bounds-check",
    "severity": "medium",
    "title": "stats_for lacks bounds check on shard index"
  },
  {
    "file": "src/config.rs",
    "line": 9,
    "category": "default-mismatch",
    "severity": "medium",
    "title": "DEFAULT_BURST is 80 instead of specified default 8"
  },
  {
    "file": "src/config.rs",
    "line": 67,
    "category": "missing-validation",
    "severity": "serious",
    "title": "rate parsing silently uses default on failure instead of returning error"
  },
  {
    "file": "src/config.rs",
    "line": 76,
    "category": "missing-validation",
    "severity": "serious",
    "title": "interval_ms parsing silently uses default on failure instead of returning error"
  },
  {
    "file": "src/api.rs",
    "line": 46,
    "category": "logic-inversion",
    "severity": "critical",
    "title": "allowlist logic inverted: rate limits apply to allowlisted keys instead of bypassing them"
  },
  {
    "file": "src/bucket.rs",
    "line": 25,
    "category": "missing-validation",
    "severity": "critical",
    "title": "TokenBucket::new missing validation for zero refill_interval_ms"
  }
]
