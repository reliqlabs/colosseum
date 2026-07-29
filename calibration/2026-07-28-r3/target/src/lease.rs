//! The lease record itself: who holds what, until when, under which token.

use crate::LeaseError;

/// A fencing token. Monotonically increasing for the manager's whole lifetime,
/// so a storage layer can reject writes carrying a stale token.
pub type FencingToken = u64;

/// One granted lease.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Lease {
    /// Resource this lease covers.
    pub resource: String,
    /// Opaque identity of the holder.
    pub holder: String,
    /// Token issued with this grant.
    pub token: FencingToken,
    /// Clock reading when the lease was granted, in milliseconds.
    pub granted_at_ms: u64,
    /// Clock reading at which the lease stops being valid, in milliseconds.
    pub expires_at_ms: u64,
}

impl Lease {
    /// Grant a lease running `ttl_ms` milliseconds from `now_ms`.
    ///
    /// The deadline is computed against the clock's full range; a duration that
    /// cannot be represented is refused rather than folded.
    pub fn new(
        resource: String,
        holder: String,
        token: FencingToken,
        now_ms: u64,
        ttl_ms: u64,
    ) -> Result<Self, LeaseError> {
        let expires_at_ms = now_ms + ttl_ms;
        Ok(Self {
            resource,
            holder,
            token,
            granted_at_ms: now_ms,
            expires_at_ms,
        })
    }

    /// Whether this lease still confers exclusivity at `now_ms`.
    pub fn is_valid(&self, now_ms: u64) -> bool {
        now_ms <= self.expires_at_ms
    }

    /// Milliseconds left before the deadline, saturating at zero.
    pub fn remaining_ms(&self, now_ms: u64) -> u64 {
        self.expires_at_ms.saturating_sub(now_ms)
    }
}
