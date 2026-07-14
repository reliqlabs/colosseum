//! Eviction (INTENT A1, A3, A6, A7).

use crate::cache::Cache;

/// Evict one entry to make room. The victim is taken from the recency
/// queue maintained by `Cache::touch` (INTENT A3).
pub(crate) fn evict_one(cache: &mut Cache) {
    let victim = match cache.order.pop_back() {
        Some(k) => k,
        None => return,
    };
    let entry = match cache.map.remove(&victim) {
        Some(e) => e,
        None => return,
    };
    cache.tombstones.push(victim.clone());
    if let Some(cb) = cache.on_evict.as_mut() {
        cb(&victim, &entry.value);
    }
}

/// Drain the tombstone log and release its storage.
pub fn compact_tombstones(cache: &mut Cache) {
    cache.tombstones.clear();
    cache.tombstones.shrink_to_fit();
}
