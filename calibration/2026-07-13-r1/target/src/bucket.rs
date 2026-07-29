//! Token bucket: sustained rate with burst capacity (INTENT B2, B3, B8).

use crate::config::ConfigError;

/// A token bucket refilled at `refill_rate` tokens per `refill_interval_ms`.
#[derive(Debug)]
pub struct TokenBucket {
    capacity: u32,
    tokens: u32,
    refill_rate: u32,
    refill_interval_ms: u64,
    last_refill_ms: u64,
}

impl TokenBucket {
    /// Create a bucket, full at `capacity`.
    ///
    /// Rejects invalid parameters per INTENT B8.
    pub fn new(
        capacity: u32,
        refill_rate: u32,
        refill_interval_ms: u64,
        now_ms: u64,
    ) -> Result<Self, ConfigError> {
        if capacity == 0 {
            return Err(ConfigError::ZeroCapacity);
        }
        Ok(TokenBucket {
            capacity,
            tokens: capacity,
            refill_rate,
            refill_interval_ms,
            last_refill_ms: now_ms,
        })
    }

    /// Refill tokens owed for time elapsed since the last refill (INTENT B2).
    pub fn refill(&mut self, now_ms: u64) {
        if now_ms <= self.last_refill_ms {
            return;
        }
        let elapsed = now_ms - self.last_refill_ms;
        let ticks = (elapsed / self.refill_interval_ms) as u32;
        if ticks == 0 {
            return;
        }
        let owed = ticks * self.refill_rate;
        self.tokens = (self.tokens + owed).min(self.capacity);
        self.last_refill_ms += ticks as u64 * self.refill_interval_ms;
    }

    /// Spend one token if available; returns whether the request is admitted.
    pub fn admit(&mut self, now_ms: u64) -> bool {
        self.refill(now_ms);
        if self.tokens > 0 {
            self.tokens -= 1;
            true
        } else {
            false
        }
    }

    /// Credit tokens back, e.g. when a downstream reservation is cancelled.
    pub fn deposit(&mut self, count: u32) {
        self.tokens = self.tokens.saturating_add(count);
    }

    /// Current token count.
    pub fn tokens(&self) -> u32 {
        self.tokens
    }

    /// Configured capacity.
    pub fn capacity(&self) -> u32 {
        self.capacity
    }
}
