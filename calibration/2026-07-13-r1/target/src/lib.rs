//! `throttle` — per-key request rate limiter.
//!
//! See INTENT.md for the behavioral contract (clauses B1-B8).

pub mod api;
pub mod bucket;
pub mod config;
pub mod window;

pub use api::Limiter;
pub use bucket::TokenBucket;
pub use config::{Config, ConfigError};
pub use window::SlidingWindow;
