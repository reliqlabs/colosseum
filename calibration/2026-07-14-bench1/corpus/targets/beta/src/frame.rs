//! Frame encoding and wire constants (INTENT P1, P2).

use crate::checksum::crc16;

pub const MAGIC: [u8; 2] = [0xA5, 0x5A];
/// Header: magic (2) + big-endian length (4).
pub const HEADER_LEN: usize = 6;
/// Trailer: big-endian CRC-16 (2).
pub const TRAILER_LEN: usize = 2;
/// Largest admissible payload in bytes (INTENT P2).
pub const MAX_PAYLOAD: usize = 65536;
/// Unconsumed-byte ceiling for the parse buffer (INTENT P3).
pub const HIGH_WATER: usize = 1 << 20;

#[derive(Debug, PartialEq, Eq)]
pub enum FrameError {
    /// Payload larger than `MAX_PAYLOAD` (P2).
    Oversize(usize),
    /// Buffered bytes would exceed `HIGH_WATER` (P3).
    Backpressure,
    /// Magic or checksum verification failed (P4).
    Corrupt { at_offset: usize },
}

/// Encode one payload into a complete frame (INTENT P1, P2).
pub fn encode(payload: &[u8]) -> Result<Vec<u8>, FrameError> {
    if payload.len() > MAX_PAYLOAD {
        return Err(FrameError::Oversize(payload.len()));
    }
    let mut out = Vec::with_capacity(HEADER_LEN + payload.len() + TRAILER_LEN);
    out.extend_from_slice(&MAGIC);
    out.extend_from_slice(&(payload.len() as u32).to_be_bytes());
    out.extend_from_slice(payload);
    out.extend_from_slice(&crc16(payload).to_be_bytes());
    Ok(out)
}
