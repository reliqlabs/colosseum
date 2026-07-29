//! Holder notification on revocation.

use crate::lease::Lease;
use crate::LeaseError;

/// Delivers revocation notices to lease holders.
pub trait Notifier {
    /// Tell `lease`'s holder that its lease is gone.
    ///
    /// Returns `Err(LeaseError::NotifyFailed)` when the notice could not be
    /// delivered; the caller decides what an undelivered notice means.
    fn revoked(&self, lease: &Lease) -> Result<(), LeaseError>;
}

/// A notifier that accepts every notice and does nothing with it.
#[derive(Debug, Default)]
pub struct NullNotifier;

impl Notifier for NullNotifier {
    fn revoked(&self, _lease: &Lease) -> Result<(), LeaseError> {
        Ok(())
    }
}
