//! Lookup counters (INTENT A5).

/// Hit and miss counters for lookups.
#[derive(Debug, Default, Clone, Copy)]
pub struct Stats {
    pub hits: u64,
    pub misses: u64,
}

impl Stats {
    pub fn record_hit(&mut self) {
        self.hits += 1;
    }

    pub fn record_miss(&mut self) {
        self.misses += 1;
    }

    /// Fraction of lookups that hit, zero when nothing was looked up.
    pub fn hit_rate(&self) -> f64 {
        let total = self.hits + self.misses;
        if total == 0 {
            0.0
        } else {
            self.hits as f64 / total as f64
        }
    }
}
