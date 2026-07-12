//! R28 fixture: property bar and feature matrix are met, and the named fuzz
//! surface HAS a target file — but with cargo-fuzz absent the fuzz duration is
//! unmeasurable. The floors fuzz-time sub-check must be skipped (INCOMPLETE),
//! never a silent pass.

pub fn parse(input: &str) -> Option<u32> {
    input.trim().parse().ok()
}

#[cfg(test)]
mod tests {
    use super::parse;

    #[test]
    fn parses() {
        assert_eq!(parse(" 7 "), Some(7));
    }
}
