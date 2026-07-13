//! The job-queue state machine (INTENT B1-B4).
//!
//! State is deliberately scalar (counts, not job identities) so the Quint
//! spec, this implementation, and the ITF replay adapter share one state
//! vocabulary: `queued`, `running`, `attempts`, `done`, `failed`,
//! `submitted`.

/// Attempt budget per job (INTENT B1). The third failed attempt is final.
pub const MAX_ATTEMPTS: u32 = 3;

#[derive(Debug, PartialEq, Eq)]
pub enum QueueError {
    /// `submit` on a queue already holding `capacity` pending jobs (B4).
    Full,
    /// `start` with no pending job or with the worker already busy.
    NotStartable,
    /// `complete`/`fail` with no job in flight.
    NotRunning,
}

/// What a `fail` call did with the in-flight job.
#[derive(Debug, PartialEq, Eq)]
pub enum FailOutcome {
    /// Attempt budget remains: the job stays in flight on its next attempt.
    Retrying,
    /// Budget exhausted: the job is permanently failed (B1 terminal).
    Exhausted,
}

/// Single-worker queue over scalar state. See INTENT.md for the contract.
#[derive(Debug)]
pub struct JobQueue {
    capacity: u32,
    queued: u32,
    running: bool,
    attempts: u32,
    done: u32,
    failed: u32,
    submitted: u32,
}

impl JobQueue {
    pub fn new(capacity: u32) -> Self {
        JobQueue {
            capacity,
            queued: 0,
            running: false,
            attempts: 0,
            done: 0,
            failed: 0,
            submitted: 0,
        }
    }

    /// Admit one job to the pending queue (INTENT B4).
    pub fn submit(&mut self) -> Result<(), QueueError> {
        if self.queued >= self.capacity {
            return Err(QueueError::Full);
        }
        self.queued += 1;
        self.submitted += 1;
        Ok(())
    }

    /// Move one pending job in flight; its first attempt begins (INTENT B3).
    pub fn start(&mut self) -> Result<(), QueueError> {
        if self.queued == 0 || self.running {
            return Err(QueueError::NotStartable);
        }
        self.queued -= 1;
        self.running = true;
        self.attempts = 1;
        Ok(())
    }

    /// The in-flight job finished successfully.
    pub fn complete(&mut self) -> Result<(), QueueError> {
        if !self.running {
            return Err(QueueError::NotRunning);
        }
        self.running = false;
        self.attempts = 0;
        self.done += 1;
        Ok(())
    }

    /// The in-flight attempt failed: retry within budget, else fail the
    /// job permanently (INTENT B1).
    pub fn fail(&mut self) -> Result<FailOutcome, QueueError> {
        if !self.running {
            return Err(QueueError::NotRunning);
        }
        if self.attempts < MAX_ATTEMPTS {
            self.attempts += 1;
            Ok(FailOutcome::Retrying)
        } else {
            self.running = false;
            self.attempts = 0;
            self.failed += 1;
            Ok(FailOutcome::Exhausted)
        }
    }

    pub fn queued(&self) -> u32 {
        self.queued
    }

    pub fn is_running(&self) -> bool {
        self.running
    }

    pub fn attempts(&self) -> u32 {
        self.attempts
    }

    pub fn done(&self) -> u32 {
        self.done
    }

    pub fn failed(&self) -> u32 {
        self.failed
    }

    pub fn submitted(&self) -> u32 {
        self.submitted
    }

    /// INTENT B2, as code: the conservation identity over the counters.
    pub fn conserved(&self) -> bool {
        let in_flight = u32::from(self.running);
        self.queued + in_flight + self.done + self.failed == self.submitted
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn b1_third_failure_is_final() {
        let mut q = JobQueue::new(4);
        q.submit().unwrap();
        q.start().unwrap();
        assert_eq!(q.fail().unwrap(), FailOutcome::Retrying); // attempt 1 fails
        assert_eq!(q.fail().unwrap(), FailOutcome::Retrying); // attempt 2 fails
        assert_eq!(q.fail().unwrap(), FailOutcome::Exhausted); // attempt 3 fails
        assert_eq!(q.failed(), 1);
        assert_eq!(q.attempts(), 0);
        assert!(q.attempts() <= MAX_ATTEMPTS);
    }

    #[test]
    fn b2_conservation_across_random_walk() {
        let mut q = JobQueue::new(3);
        // A fixed pseudo-random walk over every operation; conservation must
        // hold after every step.
        let mut seed: u64 = 0x9e3779b97f4a7c15;
        for _ in 0..500 {
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
            match seed % 4 {
                0 => {
                    let _ = q.submit();
                }
                1 => {
                    let _ = q.start();
                }
                2 => {
                    let _ = q.complete();
                }
                _ => {
                    let _ = q.fail();
                }
            }
            assert!(q.conserved(), "conservation violated: {q:?}");
            assert!(q.attempts() <= MAX_ATTEMPTS, "B1 violated: {q:?}");
            assert!(q.is_running() || q.attempts() == 0, "B3 violated: {q:?}");
            assert!(q.queued() <= 3, "B4 violated: {q:?}");
        }
    }

    #[test]
    fn b3_idle_worker_has_zero_attempts() {
        let mut q = JobQueue::new(2);
        assert_eq!(q.attempts(), 0);
        q.submit().unwrap();
        q.start().unwrap();
        assert_eq!(q.attempts(), 1);
        q.complete().unwrap();
        assert_eq!(q.attempts(), 0);
    }

    #[test]
    fn b4_submit_beyond_capacity_rejected() {
        let mut q = JobQueue::new(2);
        q.submit().unwrap();
        q.submit().unwrap();
        assert_eq!(q.submit(), Err(QueueError::Full));
        assert_eq!(q.queued(), 2);
    }

    #[test]
    fn w1_a_job_can_complete() {
        let mut q = JobQueue::new(1);
        q.submit().unwrap();
        q.start().unwrap();
        q.complete().unwrap();
        assert_eq!(q.done(), 1);
    }

    #[test]
    fn guards_reject_out_of_order_operations() {
        let mut q = JobQueue::new(1);
        assert_eq!(q.start(), Err(QueueError::NotStartable));
        assert_eq!(q.complete(), Err(QueueError::NotRunning));
        assert_eq!(q.fail(), Err(QueueError::NotRunning));
        q.submit().unwrap();
        q.start().unwrap();
        assert_eq!(q.start(), Err(QueueError::NotStartable));
    }
}

#[cfg(kani)]
mod verification {
    use super::*;

    /// B1/B2/B3/B4 hold after any bounded sequence of operations.
    #[cfg_attr(kani, kani::proof)]
    #[cfg_attr(kani, kani::unwind(12))]
    fn invariants_hold_under_any_op_sequence() {
        let capacity: u32 = kani::any();
        kani::assume(capacity >= 1 && capacity <= 4);
        let mut q = JobQueue::new(capacity);
        for _ in 0..10 {
            let op: u8 = kani::any();
            match op % 4 {
                0 => {
                    let _ = q.submit();
                }
                1 => {
                    let _ = q.start();
                }
                2 => {
                    let _ = q.complete();
                }
                _ => {
                    let _ = q.fail();
                }
            }
            assert!(q.attempts() <= MAX_ATTEMPTS); // B1
            assert!(q.conserved()); // B2
            assert!(q.is_running() || q.attempts() == 0); // B3
            assert!(q.queued() <= capacity); // B4
        }
    }
}
