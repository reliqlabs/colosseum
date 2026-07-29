//! `leasedb` grants time-bounded exclusive leases over named resources.
//!
//! A caller acquires a lease on a resource, receives a fencing token, renews
//! the lease while it still needs the resource, and releases it when done. A
//! reaper collects leases whose deadline has passed and notifies their holders.
//!
//! The behavioral contract this crate implements is `INTENT.md`.

pub mod api;
pub mod lease;
pub mod notify;
pub mod reaper;
pub mod tokens;

pub use api::LeaseManager;
pub use lease::{FencingToken, Lease};
pub use notify::{NullNotifier, Notifier};

/// Every way a lease operation can fail.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LeaseError {
    /// The resource already has a live lease held by someone else.
    Held,
    /// No lease exists for the named resource.
    NotFound,
    /// The manager is holding as many leases as it is configured to hold.
    AtCapacity,
    /// A zero lease duration was requested.
    ZeroTtl,
    /// The requested duration would push the deadline past the clock's range.
    TtlOverflow,
    /// The presented fencing token is not the lease's current token.
    BadToken,
    /// A revocation notification could not be delivered.
    NotifyFailed,
}
