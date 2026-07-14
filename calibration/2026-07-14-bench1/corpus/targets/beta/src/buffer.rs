//! The incremental receive buffer (INTENT P3, P6).

use crate::frame::{FrameError, HIGH_WATER};

/// A byte buffer with a read cursor. Consumed bytes are reclaimed by
/// compaction, which must preserve every unread byte (INTENT P6).
pub struct RecvBuffer {
    bytes: Vec<u8>,
    read_pos: usize,
}

impl RecvBuffer {
    pub fn new() -> Self {
        RecvBuffer {
            bytes: Vec::new(),
            read_pos: 0,
        }
    }

    /// Number of unconsumed bytes.
    pub fn available(&self) -> usize {
        self.bytes.len() - self.read_pos
    }

    /// Append a chunk, honoring the backpressure bound (INTENT P3).
    pub fn feed(&mut self, chunk: &[u8]) -> Result<(), FrameError> {
        if self.available() + chunk.len() > HIGH_WATER {
            return Err(FrameError::Backpressure);
        }
        self.bytes.extend_from_slice(chunk);
        Ok(())
    }

    /// Unconsumed bytes as a slice.
    pub fn peek(&self) -> &[u8] {
        &self.bytes[self.read_pos..]
    }

    /// Advance the read cursor by `n` consumed bytes.
    pub fn consume(&mut self, n: usize) {
        self.read_pos += n;
        if self.read_pos >= self.bytes.len() {
            self.bytes.clear();
            self.read_pos = 0;
        }
    }

    /// Reclaim the consumed prefix while preserving unread bytes (P6).
    pub fn compact(&mut self) {
        if self.read_pos == 0 {
            return;
        }
        self.bytes.drain(..self.read_pos);
        self.read_pos = 0;
    }
}

impl Default for RecvBuffer {
    fn default() -> Self {
        Self::new()
    }
}
