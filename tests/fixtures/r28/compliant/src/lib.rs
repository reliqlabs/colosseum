//! R28 fixture: MEETS the engineering baseline floors.
//! Public API carries an in-file test, floors.json declares a feature matrix
//! whose combos compile, and names no fuzz surfaces (so the fuzz-time floor is
//! not_applicable and the layer passes without cargo-fuzz).

pub fn parse(input: &str) -> Option<u32> {
    input.trim().parse().ok()
}

#[cfg(test)]
mod tests {
    use super::parse;

    #[test]
    fn parses() {
        assert_eq!(parse(" 42 "), Some(42));
        assert_eq!(parse("nope"), None);
    }
}
