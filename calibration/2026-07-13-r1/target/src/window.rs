//! Sliding window: hard cap on events per interval (INTENT B1).

use std::collections::VecDeque;

/// Sliding-window event log capping admits at `limit` per `window_ms`.
#[derive(Debug)]
pub struct SlidingWindow {
    limit: usize,
    window_ms: u64,
    events: VecDeque<u64>,
}

impl SlidingWindow {
    pub fn new(limit: usize, window_ms: u64) -> Self {
        SlidingWindow {
            limit,
            window_ms,
            events: VecDeque::new(),
        }
    }

    /// Drop events that have aged out of the window.
    fn prune(&mut self, now_ms: u64) {
        let cutoff = now_ms.saturating_sub(self.window_ms);
        while let Some(&oldest) = self.events.front() {
            if oldest < cutoff {
                self.events.pop_front();
            } else {
                break;
            }
        }
    }

    /// Admit the event if the window cap allows it (INTENT B1).
    pub fn admit(&mut self, now_ms: u64) -> bool {
        self.prune(now_ms);
        if self.events.len() <= self.limit {
            self.events.push_back(now_ms);
            true
        } else {
            false
        }
    }

    /// Events currently inside the window.
    pub fn occupancy(&self) -> usize {
        self.events.len()
    }
}
