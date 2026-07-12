//! Fixture library crate for R17: a Kani harness in the
//! `#[cfg_attr(kani, kani::proof)]` form plus a `#[kani::proof_for_contract]`
//! occurrence for discovery. There is no `main`; the only working
//! verification path is the library one (verus --crate-type=lib / cargo kani).

pub fn add(a: u32, b: u32) -> u32 {
    a + b
}

// cfg-gated so `cargo build`/`cargo test` (kani cfg unset) strip it; under
// `cargo kani` it is a live, trivially provable harness.
#[cfg(kani)]
#[cfg_attr(kani, kani::proof)]
fn check_add_commutes() {
    let a: u32 = kani::any();
    let b: u32 = kani::any();
    kani::assume(a <= 1000);
    kani::assume(b <= 1000);
    assert_eq!(add(a, b), add(b, a));
}

// Contract harness, feature-gated off so it is not compiled here (that path
// needs -Zfunction-contracts). Present purely so discovery finds the
// `#[kani::proof_for_contract(...)]` form.
#[cfg(feature = "kani_contracts")]
mod contract_harnesses {
    use super::*;

    #[kani::requires(x < 1_000_000)]
    #[kani::ensures(|r: &u32| *r == x + 1)]
    fn inc(x: u32) -> u32 {
        x + 1
    }

    #[kani::proof_for_contract(inc)]
    fn check_inc_contract() {
        let x: u32 = kani::any();
        inc(x);
    }
}
