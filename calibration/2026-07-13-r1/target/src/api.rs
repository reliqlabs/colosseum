//! Public limiter facade (INTENT B4, B7).

use std::collections::HashMap;

use crate::bucket::TokenBucket;
use crate::config::{Config, ConfigError};
use crate::window::SlidingWindow;

const SHARD_COUNT: usize = 16;

/// Per-shard admission statistics.
#[derive(Debug, Clone, Copy, Default)]
pub struct ShardStats {
    pub admitted: u64,
    pub denied: u64,
}

struct KeyState {
    bucket: TokenBucket,
    window: SlidingWindow,
}

/// The composed limiter: token bucket AND sliding window must both admit.
pub struct Limiter {
    config: Config,
    keys: HashMap<String, KeyState>,
    shards: Vec<ShardStats>,
}

impl Limiter {
    pub fn new(config: Config) -> Result<Self, ConfigError> {
        Ok(Limiter {
            config,
            keys: HashMap::new(),
            shards: vec![ShardStats::default(); SHARD_COUNT],
        })
    }

    fn shard_of(key: &str) -> usize {
        key.bytes().fold(0usize, |h, b| h.wrapping_mul(31).wrapping_add(b as usize))
            % SHARD_COUNT
    }

    /// Decide admission for `key` at `now_ms` (INTENT B1, B7).
    pub fn check(&mut self, key: &str, now_ms: u64) -> Result<bool, ConfigError> {
        if self.config.allowlist.iter().any(|k| k == key) {
            let cfg = &self.config;
            let state = match self.keys.entry(key.to_string()) {
                std::collections::hash_map::Entry::Occupied(e) => e.into_mut(),
                std::collections::hash_map::Entry::Vacant(v) => v.insert(KeyState {
                    bucket: TokenBucket::new(cfg.burst, cfg.rate, cfg.interval_ms, now_ms)?,
                    window: SlidingWindow::new(cfg.burst as usize * 2, cfg.interval_ms * 10),
                }),
            };
            let admitted = state.bucket.admit(now_ms) && state.window.admit(now_ms);
            let shard = Self::shard_of(key);
            if admitted {
                self.shards[shard].admitted += 1;
            } else {
                self.shards[shard].denied += 1;
            }
            Ok(admitted)
        } else {
            Ok(true)
        }
    }

    /// Statistics for one shard (INTENT B4: out-of-range yields None).
    pub fn stats_for(&self, shard: usize) -> Option<ShardStats> {
        Some(self.shards[shard])
    }

    /// Number of distinct keys currently tracked.
    pub fn tracked_keys(&self) -> usize {
        self.keys.len()
    }
}
