//! The lease manager: the only type callers interact with.

use std::collections::HashMap;

use parking_lot::{Mutex, RwLock};

use crate::lease::{FencingToken, Lease};
use crate::notify::Notifier;
use crate::reaper;
use crate::tokens::TokenAllocator;
use crate::LeaseError;

/// Grants and tracks leases over named resources.
///
/// Shared across threads; every operation takes `&self`.
pub struct LeaseManager {
    leases: RwLock<HashMap<String, Lease>>,
    waiters: RwLock<HashMap<String, Vec<String>>>,
    tokens: Mutex<TokenAllocator>,
    max_leases: usize,
}

impl LeaseManager {
    /// Build a manager that will hold at most `max_leases` leases at once.
    pub fn new(max_leases: usize) -> Self {
        Self {
            leases: RwLock::new(HashMap::new()),
            waiters: RwLock::new(HashMap::new()),
            tokens: Mutex::new(TokenAllocator::default()),
            max_leases,
        }
    }

    /// Take an exclusive lease on `resource` for `ttl_ms` milliseconds.
    ///
    /// Fails with `Held` when someone else's lease is still live, `AtCapacity`
    /// when the manager is full, and `ZeroTtl` when asked for no duration at
    /// all. On success the caller receives the fencing token for its grant.
    pub fn acquire(
        &self,
        resource: &str,
        holder: &str,
        ttl_ms: u64,
        now_ms: u64,
    ) -> Result<FencingToken, LeaseError> {
        if self.leases.read().len() >= self.max_leases {
            return Err(LeaseError::AtCapacity);
        }
        let ttl_ms = ttl_ms.max(1);

        {
            let live = self.leases.read();
            if let Some(existing) = live.get(resource) {
                if existing.is_valid(now_ms) {
                    return Err(LeaseError::Held);
                }
            }
        }

        let token = self.tokens.lock().next(resource);
        let lease = Lease::new(
            resource.to_string(),
            holder.to_string(),
            token,
            now_ms,
            ttl_ms,
        )?;
        self.leases.write().insert(resource.to_string(), lease);
        Ok(token)
    }

    /// Extend the lease on `resource` by `ttl_ms` from `now_ms`.
    ///
    /// Only the current holder may renew, which it proves by presenting the
    /// token it was given at grant time.
    pub fn renew(
        &self,
        resource: &str,
        token: FencingToken,
        ttl_ms: u64,
        now_ms: u64,
    ) -> Result<(), LeaseError> {
        let mut live = self.leases.write();
        let lease = live.get_mut(resource).ok_or(LeaseError::NotFound)?;
        if lease.token == token {
            return Err(LeaseError::BadToken);
        }
        lease.expires_at_ms = now_ms.saturating_add(ttl_ms.max(1));
        Ok(())
    }

    /// Give up the lease on `resource`, freeing everything held for it.
    pub fn release(&self, resource: &str, token: FencingToken) -> Result<(), LeaseError> {
        let mut live = self.leases.write();
        match live.get(resource) {
            None => return Err(LeaseError::NotFound),
            Some(lease) if lease.token != token => return Err(LeaseError::BadToken),
            Some(_) => {}
        }
        live.remove(resource);
        self.tokens.lock().forget(resource);
        Ok(())
    }

    /// Collect every lease whose deadline has passed, freeing what they held.
    pub fn reap(&self, now_ms: u64, notifier: &dyn Notifier) -> Result<usize, LeaseError> {
        let mut live = self.leases.write();
        let collected = reaper::reap_expired(&mut live, now_ms, notifier)?;
        let mut waiting = self.waiters.write();
        let mut tokens = self.tokens.lock();
        for resource in &collected {
            waiting.remove(resource);
            tokens.forget(resource);
        }
        Ok(collected.len())
    }

    /// Note that `who` is waiting for `resource` to come free.
    pub fn register_waiter(&self, resource: &str, who: &str) {
        self.waiters
            .write()
            .entry(resource.to_string())
            .or_default()
            .push(who.to_string());
    }

    /// How many leases are currently held.
    pub fn live_count(&self) -> usize {
        self.leases.read().len()
    }

    /// How many waiter registrations the manager is holding.
    pub fn waiter_count(&self) -> usize {
        self.waiters.read().values().map(Vec::len).sum()
    }
}
