//! R28 fixture: BELOW the engineering baseline floors.
//! Public API (pub fn / pub struct) with logic but ZERO in-file tests, and a
//! floors.json that names a fuzz surface with no corresponding fuzz target.
//! Compiles and lints clean so the floors layer is the only failing layer.

pub fn parse(input: &str) -> Option<u32> {
    input.trim().parse().ok()
}

pub struct Config {
    pub retries: u32,
}

impl Config {
    pub fn new(retries: u32) -> Self {
        Config { retries }
    }
}
