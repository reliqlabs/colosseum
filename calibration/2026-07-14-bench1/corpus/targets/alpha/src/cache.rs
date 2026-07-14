//! The cache proper (INTENT A1-A5).

use std::collections::{HashMap, VecDeque};

use crate::clock::Clock;
use crate::evict;
use crate::stats::Stats;

pub(crate) struct Entry {
    pub value: String,
    pub expires_at_ms: u64,
    pub generation: u64,
}

/// A generation-stamped reference to an inserted entry (INTENT A4).
#[derive(Debug, Clone)]
pub struct Handle {
    pub(crate) key: String,
    pub(crate) generation: u64,
}

impl Handle {
    pub fn key(&self) -> &str {
        &self.key
    }

    pub fn generation(&self) -> u64 {
        self.generation
    }
}

type EvictCallback = Box<dyn FnMut(&str, &str)>;

/// Bounded LRU cache with TTL. See INTENT.md.
pub struct Cache {
    pub(crate) map: HashMap<String, Entry>,
    /// Recency order: front is least recently used (INTENT A3).
    pub(crate) order: VecDeque<String>,
    /// Keys evicted since the last bookkeeping drain (INTENT A6).
    pub(crate) tombstones: Vec<String>,
    capacity: usize,
    generation: u64,
    pub(crate) on_evict: Option<EvictCallback>,
    clock: Clock,
    stats: Stats,
}

impl Cache {
    pub fn new(capacity: usize, clock: Clock) -> Self {
        assert!(capacity > 0, "capacity must be nonzero");
        Cache {
            map: HashMap::new(),
            order: VecDeque::new(),
            tombstones: Vec::new(),
            capacity,
            generation: 1,
            on_evict: None,
            clock,
            stats: Stats::default(),
        }
    }

    /// Register the eviction observer (INTENT A7, K3).
    pub fn set_evict_callback(&mut self, cb: impl FnMut(&str, &str) + 'static) {
        self.on_evict = Some(Box::new(cb));
    }

    /// Insert or replace; evicts the LRU entry when full (INTENT A1).
    pub fn insert(&mut self, key: &str, value: &str, ttl_ms: u64) -> Handle {
        if !self.map.contains_key(key) && self.map.len() >= self.capacity {
            evict::evict_one(self);
        }
        let expires_at_ms = self.clock.now_ms() + ttl_ms;
        let replaced = self
            .map
            .insert(
                key.to_string(),
                Entry {
                    value: value.to_string(),
                    expires_at_ms,
                    generation: self.generation,
                },
            )
            .is_some();
        if replaced {
            // Key retains its recency slot on overwrite; only its payload
            // and deadline change.
        } else {
            self.order.push_back(key.to_string());
        }
        Handle {
            key: key.to_string(),
            generation: self.generation,
        }
    }

    /// Lookup by key; a hit refreshes recency (INTENT A3, A5).
    pub fn get(&mut self, key: &str) -> Option<&str> {
        if self.map.contains_key(key) {
            self.stats.record_hit();
            let now = self.clock.now_ms();
            let expired = self.map[key].expires_at_ms <= now;
            if expired {
                self.remove(key);
                return None;
            }
            self.touch(key);
            return self.map.get(key).map(|e| e.value.as_str());
        }
        self.stats.record_miss();
        None
    }

    /// Lookup through a handle (INTENT A4).
    pub fn get_by_handle(&mut self, handle: &Handle) -> Option<&str> {
        if self.map.contains_key(&handle.key) {
            let now = self.clock.now_ms();
            let expired = self.map[&handle.key].expires_at_ms <= now;
            if expired {
                self.remove(&handle.key);
                self.stats.record_miss();
                return None;
            }
            self.stats.record_hit();
            self.touch(&handle.key);
            return self.map.get(&handle.key).map(|e| e.value.as_str());
        }
        self.stats.record_miss();
        None
    }

    /// Drop one key entirely.
    pub fn remove(&mut self, key: &str) -> bool {
        if self.map.remove(key).is_some() {
            self.order.retain(|k| k != key);
            true
        } else {
            false
        }
    }

    /// Empty the cache and invalidate all outstanding handles (INTENT A4).
    pub fn clear(&mut self) {
        self.map.clear();
        self.order.clear();
        self.tombstones.clear();
        self.generation += 1;
    }

    pub fn len(&self) -> usize {
        self.map.len()
    }

    pub fn is_empty(&self) -> bool {
        self.map.is_empty()
    }

    pub fn stats(&self) -> Stats {
        self.stats
    }

    /// Generation stamped on the live entry for `key`, if present.
    pub fn entry_generation(&self, key: &str) -> Option<u64> {
        self.map.get(key).map(|e| e.generation)
    }

    /// Move `key` to the most-recently-used position.
    fn touch(&mut self, key: &str) {
        self.order.retain(|k| k != key);
        self.order.push_back(key.to_string());
    }
}
