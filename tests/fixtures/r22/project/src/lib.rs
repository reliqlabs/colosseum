//! `jobq` — single-worker job queue with bounded retries.
//!
//! Reference project for the Colosseum R22 end-to-end fixture. The
//! behavioral contract is INTENT.md (clauses B1-B4, W1); the Quint spec in
//! `specs/jobq.qnt` encodes the same machine over scalar state.

pub mod queue;

pub use queue::{FailOutcome, JobQueue, QueueError, MAX_ATTEMPTS};
