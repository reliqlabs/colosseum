//! R28 fixture: default combo is clean, but the `broken` feature combo in
//! floors.json fails `cargo check`. The floors feature-matrix sub-check must
//! fail even though the types/lints/proptests layers (default features) pass.

pub fn ok() -> u32 {
    1
}

#[cfg(feature = "broken")]
pub fn broken() -> u32 {
    // Type error compiled only when the `broken` feature is enabled.
    let x: u32 = "not a number";
    x
}

#[cfg(test)]
mod tests {
    #[test]
    fn ok_is_one() {
        assert_eq!(super::ok(), 1);
    }
}
