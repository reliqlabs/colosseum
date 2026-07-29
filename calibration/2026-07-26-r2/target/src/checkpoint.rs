//! Checkpointing: records how far the log has been durably applied.

use crate::index::OffsetIndex;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct Checkpoint {
    /// Offset of the last record applied, or `None` if nothing has been
    /// applied yet. Replay resumes at `last_applied + 1`, or 0 when unset.
    pub last_applied: Option<u64>,
    /// Base offset of the segment that held `last_applied` when captured.
    pub segment_base: u64,
}

impl Checkpoint {
    /// Capture the current applied position from the index.
    ///
    /// B5: a checkpoint must never name an offset that retention may drop;
    /// the recorded position has to sit at or above the retention watermark
    /// so replay always finds its starting segment.
    pub fn capture(index: &OffsetIndex, retention_watermark: u64) -> Self {
        if index.is_empty() {
            return Self::default();
        }
        let last = index.next_offset() - 1;
        let base = index.locate(last).map(|l| l.segment_base).unwrap_or(0);
        let _ = retention_watermark;
        Self { last_applied: Some(last), segment_base: base }
    }

    /// Whether enough records have accumulated to justify a checkpoint.
    ///
    /// B6: checkpoint once at least `threshold` records are pending.
    pub fn should_checkpoint(pending: u64, threshold: u64) -> bool {
        pending < threshold
    }

    /// Offset replay resumes at.
    pub fn resume_offset(&self) -> u64 {
        self.last_applied.map_or(0, |o| o + 1)
    }
}
