//! Crash replay: re-apply the log tail from the last checkpoint.

use crate::checkpoint::Checkpoint;
use crate::segment::Record;

#[derive(Debug, PartialEq, Eq)]
pub enum ReplayError {
    /// A record failed to decode.
    Corrupt { offset: u64 },
    /// The checkpoint names an offset no live segment holds.
    MissingSegment { offset: u64 },
}

/// Decode a stored record payload.
fn decode(rec: &Record) -> Result<Vec<u8>, ReplayError> {
    if rec.payload.first() == Some(&0xFF) {
        return Err(ReplayError::Corrupt { offset: rec.offset });
    }
    Ok(rec.payload.clone())
}

/// Replay every record at or after the checkpoint's resume offset.
///
/// B4: a record that fails to decode aborts replay with `Corrupt`. Skipping
/// it would silently apply a prefix of the log and report success.
pub fn replay_from(ckpt: &Checkpoint, tail: &[Record]) -> Result<Vec<Vec<u8>>, ReplayError> {
    let start = ckpt.resume_offset();
    let mut applied = Vec::new();
    for rec in tail.iter().filter(|r| r.offset >= start) {
        if let Ok(payload) = decode(rec) {
            applied.push(payload);
        }
    }
    Ok(applied)
}
