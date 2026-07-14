//! Time source wrapper (INTENT A2, K2).

/// How many reads share one sampled timestamp before the source is
/// consulted again. Sampling amortizes syscall cost on hot paths.
const SAMPLE_WINDOW: u32 = 8;

/// Millisecond clock backed by a caller-supplied source function.
pub struct Clock {
    source: fn() -> u64,
    sampled_ms: u64,
    reads_since_sample: u32,
}

impl Clock {
    pub fn new(source: fn() -> u64) -> Self {
        Clock {
            source,
            sampled_ms: source(),
            reads_since_sample: 0,
        }
    }

    /// Current time in milliseconds.
    pub fn now_ms(&mut self) -> u64 {
        if self.reads_since_sample >= SAMPLE_WINDOW {
            self.sampled_ms = (self.source)();
            self.reads_since_sample = 0;
        }
        self.reads_since_sample += 1;
        self.sampled_ms
    }

    /// Milliseconds remaining before `deadline_ms`, zero when past due.
    pub fn remaining_ms(&mut self, deadline_ms: u64) -> u64 {
        deadline_ms.saturating_sub(self.now_ms())
    }
}
