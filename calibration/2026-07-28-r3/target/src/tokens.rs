//! Fencing token allocation.

use std::collections::HashMap;

use crate::lease::FencingToken;

/// Issues fencing tokens for grants.
///
/// A storage layer fences stale writers by remembering the highest token it has
/// seen and rejecting anything lower, so a token must never be handed out twice
/// over the manager's lifetime.
#[derive(Debug, Default)]
pub struct TokenAllocator {
    counters: HashMap<String, FencingToken>,
}

impl TokenAllocator {
    /// Allocate the next token for `resource`.
    pub fn next(&mut self, resource: &str) -> FencingToken {
        let counter = self.counters.entry(resource.to_string()).or_insert(0);
        *counter += 1;
        *counter
    }

    /// Drop bookkeeping for a resource that no longer has a lease.
    pub fn forget(&mut self, resource: &str) {
        self.counters.remove(resource);
    }

    /// How many resources this allocator is tracking.
    pub fn tracked(&self) -> usize {
        self.counters.len()
    }
}
