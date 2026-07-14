//! `lru-ttl` — bounded LRU cache with TTL and generation handles.
//!
//! Contract: INTENT.md (clauses A1-A7).

pub mod cache;
pub mod clock;
pub mod evict;
pub mod stats;

pub use cache::{Cache, Handle};
pub use clock::Clock;
pub use stats::Stats;
