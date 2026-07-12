pub fn check_attestation(x: u32) -> bool {
    x != 0
}

#[kani::proof]
fn harness_check() {
    assert!(check_attestation(1));
}
