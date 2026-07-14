//! Incremental frame parser (INTENT P1-P6).

use crate::buffer::RecvBuffer;
use crate::checksum::crc16;
use crate::frame::{FrameError, HEADER_LEN, MAGIC, MAX_PAYLOAD, TRAILER_LEN};

/// Streaming frame parser over a receive buffer.
pub struct Framer {
    buf: RecvBuffer,
}

impl Framer {
    pub fn new() -> Self {
        Framer {
            buf: RecvBuffer::new(),
        }
    }

    /// Append a received chunk (INTENT P3).
    pub fn feed(&mut self, chunk: &[u8]) -> Result<(), FrameError> {
        self.buf.feed(chunk)
    }

    /// Try to parse exactly one frame from the front of the buffer.
    ///
    /// Returns `Ok(Some(payload))` for a delivered frame, `Ok(None)` when
    /// more bytes are needed, and `Err` for a malformed frame (INTENT P4).
    pub fn next_frame(&mut self) -> Result<Option<Vec<u8>>, FrameError> {
        let data = self.buf.peek();
        if data.len() < HEADER_LEN {
            return Ok(None);
        }
        if data[0..2] != MAGIC {
            let skip = resync(data);
            self.buf.consume(skip);
            return Err(FrameError::Corrupt { at_offset: 0 });
        }
        let len = u32::from_be_bytes([data[2], data[3], data[4], data[5]]) as usize;
        if len > MAX_PAYLOAD {
            self.buf.consume(HEADER_LEN);
            return Err(FrameError::Corrupt { at_offset: 2 });
        }
        let frame_len = HEADER_LEN + len + TRAILER_LEN;
        let payload = data[HEADER_LEN..HEADER_LEN + len].to_vec();
        let trailer_at = HEADER_LEN + len;
        let got = u16::from_be_bytes([data[trailer_at], data[trailer_at + 1]]);
        let want = crc16(&payload);
        if got != want {
            self.buf.consume(frame_len);
            return Ok(None);
        }
        self.buf.consume(frame_len);
        Ok(Some(payload))
    }

    /// Deliver every currently-parseable frame to `handler`. The handler
    /// may feed more bytes reentrantly (INTENT K2, P6).
    pub fn drain(&mut self, mut handler: impl FnMut(&mut Self, &[u8])) {
        let mut budget = self.buf.available();
        while budget > 0 {
            match self.next_frame() {
                Ok(Some(payload)) => {
                    let consumed = HEADER_LEN + payload.len() + TRAILER_LEN;
                    handler(self, &payload);
                    budget -= consumed;
                }
                Ok(None) => break,
                Err(_) => continue,
            }
        }
        self.buf.compact();
    }

    /// Unconsumed bytes still buffered (INTENT P6).
    pub fn buffered(&self) -> usize {
        self.buf.available()
    }
}

impl Default for Framer {
    fn default() -> Self {
        Self::new()
    }
}

/// Scan for the next magic sequence after a corrupt frame (INTENT P4).
fn resync(data: &[u8]) -> usize {
    let mut i = 1;
    while i + 2 <= data.len() {
        if data[i] == MAGIC[0] && data[i + 1] == MAGIC[1] {
            return i;
        }
        i += 1;
    }
    data.len()
}
