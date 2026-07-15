// Fixture source for the m3b benchmark-runner test. Content is inert: the stub
// dispatcher does not read it, but a real target crate would carry real code
// here and the planted defects would live at the corpus line numbers.

pub fn count_up(n: usize) -> usize {
    let mut total = 0;
    // line 10 region: seeded off-by-one (D1)
    for i in 0..=n {
        total += i;
    }
    // line 20 region: seeded unchecked-arithmetic (D2)
    let bumped = total + 1;
    bumped
}
