//! `ledger` — an append-only, segmented event log.
//!
//! Records are appended at monotonically increasing offsets. Records live in
//! fixed-size segments; an in-memory index maps an offset to the segment that
//! holds it. A checkpoint records how far the log has been applied so a crash
//! can replay only the tail. See INTENT.md for the behavioral contract.

pub mod api;
pub mod checkpoint;
pub mod index;
pub mod replay;
pub mod segment;

pub use api::{Ledger, LedgerConfig, LedgerError};
pub use checkpoint::Checkpoint;
pub use index::{Location, OffsetIndex};
pub use replay::{replay_from, ReplayError};
pub use segment::{Segment, SegmentError};
