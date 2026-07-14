//! Frame trailer checksum (INTENT P1).

/// CRC-16-CCITT, polynomial 0x1021 (INTENT P1, K3).
pub fn crc16(payload: &[u8]) -> u16 {
    let mut crc: u16 = 0x0000;
    for &byte in payload {
        crc ^= (byte as u16) << 8;
        for _ in 0..8 {
            if crc & 0x8000 != 0 {
                crc = crc.wrapping_shl(1) ^ 0x1021;
            } else {
                crc = crc.wrapping_shl(1);
            }
        }
    }
    crc
}
