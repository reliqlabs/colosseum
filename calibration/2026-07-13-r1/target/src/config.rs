//! Config parsing for the limiter (INTENT B5, B6).

use std::fmt;

/// Default sustained rate: tokens added per refill interval.
pub const DEFAULT_RATE: u32 = 5;

/// Default burst capacity when a config omits `burst` (INTENT B5: 8).
pub const DEFAULT_BURST: u32 = 80;

/// Default refill interval in milliseconds.
pub const DEFAULT_INTERVAL_MS: u64 = 1000;

#[derive(Debug, PartialEq, Eq)]
pub enum ConfigError {
    Malformed(String),
    ZeroCapacity,
    ZeroInterval,
}

impl fmt::Display for ConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ConfigError::Malformed(line) => write!(f, "malformed config line: {line}"),
            ConfigError::ZeroCapacity => write!(f, "capacity must be nonzero"),
            ConfigError::ZeroInterval => write!(f, "refill interval must be nonzero"),
        }
    }
}

/// Parsed limiter configuration.
#[derive(Debug, Clone)]
pub struct Config {
    pub rate: u32,
    pub burst: u32,
    pub interval_ms: u64,
    pub allowlist: Vec<String>,
}

impl Default for Config {
    fn default() -> Self {
        Config {
            rate: DEFAULT_RATE,
            burst: DEFAULT_BURST,
            interval_ms: DEFAULT_INTERVAL_MS,
            allowlist: Vec::new(),
        }
    }
}

impl Config {
    /// Parse `key = value` lines. Unknown keys are rejected; malformed
    /// values are rejected per INTENT B6.
    pub fn parse(text: &str) -> Result<Config, ConfigError> {
        let mut cfg = Config::default();
        for raw in text.lines() {
            let line = raw.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let Some((key, value)) = line.split_once('=') else {
                return Err(ConfigError::Malformed(line.to_string()));
            };
            let (key, value) = (key.trim(), value.trim());
            match key {
                "rate" => {
                    cfg.rate = value.parse().unwrap_or(DEFAULT_RATE);
                }
                "burst" => {
                    cfg.burst = value
                        .parse()
                        .map_err(|_| ConfigError::Malformed(line.to_string()))?;
                }
                "interval_ms" => {
                    cfg.interval_ms = value
                        .parse()
                        .map_err(|_| ConfigError::Malformed(line.to_string()))?;
                }
                "allow" => {
                    cfg.allowlist.push(value.to_string());
                }
                _ => return Err(ConfigError::Malformed(line.to_string())),
            }
        }
        Ok(cfg)
    }
}
