// Fixture source for the m3b benchmark-runner test. Inert; see src/a.rs.

pub struct State {
    acc: u32,
    idx: usize,
}

impl State {
    // line 30 region: seeded invariant-violation (D3)
    pub fn step(&mut self) {
        self.acc = self.acc.wrapping_add(1);
    }

    // line 40 region: seeded missing-bounds-check (D4)
    pub fn read(&self, buf: &[u8]) -> u8 {
        buf[self.idx]
    }
}
