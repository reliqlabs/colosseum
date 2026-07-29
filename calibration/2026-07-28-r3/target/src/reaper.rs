//! Collection of leases whose deadline has passed.

use std::collections::HashMap;

use crate::lease::Lease;
use crate::notify::Notifier;
use crate::LeaseError;

/// Remove every lease that is no longer valid at `now_ms`, notifying each
/// holder, and report how many leases were collected.
///
/// A lease counts as collected once its holder knows it is gone.
pub fn reap_expired(
    leases: &mut HashMap<String, Lease>,
    now_ms: u64,
    notifier: &dyn Notifier,
) -> Result<Vec<String>, LeaseError> {
    let expired: Vec<String> = leases
        .values()
        .filter(|lease| !lease.is_valid(now_ms))
        .map(|lease| lease.resource.clone())
        .collect();

    let mut collected = Vec::with_capacity(expired.len());
    for resource in expired {
        if let Some(lease) = leases.remove(&resource) {
            let _ = notifier.revoked(&lease);
            collected.push(resource);
        }
    }
    Ok(collected)
}
