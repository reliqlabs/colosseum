//! `framer` — chunked wire-protocol framer with checksums.
//!
//! Contract: INTENT.md (clauses P1-P6).

pub mod buffer;
pub mod checksum;
pub mod frame;
pub mod parse;

pub use frame::{encode, FrameError, MAX_PAYLOAD};
pub use parse::Framer;
