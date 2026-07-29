# leasedb: behavioral contract

`leasedb` hands out time-bounded exclusive leases over named resources. A
caller acquires a lease, receives a fencing token, renews while it still needs
the resource, and releases when finished. A reaper collects leases whose
deadline has passed and notifies the holders it dispossessed.

Time is supplied by the caller as a millisecond reading (`now_ms`). The crate
never reads a clock itself, so a test or a simulation can drive it directly.
The manager is shared across threads: every operation takes `&self`, and all
of the guarantees below are required to hold under concurrent callers.

## Vocabulary

- **Resource** — an opaque name. Two callers naming the same string are
  contending for the same thing.
- **Holder** — an opaque identity string. `leasedb` never interprets it.
- **Live** — a lease whose deadline has not yet been reached.
- **Fencing token** — an integer handed out with each grant. A storage layer
  fences stale writers by remembering the highest token it has accepted and
  rejecting anything lower.

## Behavioral clauses

**B1 (mutual exclusion).** At most one live lease exists for a resource at any
instant. `acquire` on a resource that already has a live lease fails with
`Held` and grants nothing. This holds regardless of how many callers acquire
concurrently: two simultaneous acquirers of one resource produce exactly one
grant and one `Held`.

**B2 (duration validation).** `acquire` rejects a zero duration with `ZeroTtl`.
A zero-length lease is a caller error and is never silently widened to a
non-zero duration.

**B3 (deadline boundary).** A lease is live strictly before its deadline. At
the instant `now_ms` equals the deadline the lease has expired: it no longer
confers exclusivity and is eligible for collection.

**B4 (token monotonicity).** Fencing tokens strictly increase over the
manager's entire lifetime and are never issued twice. Releasing a lease,
collecting it, or dropping any per-resource bookkeeping does not permit a
later grant to reuse a token that was issued earlier.

**B5 (renewal authority).** `renew` succeeds exactly when a lease record exists
for the resource and the presented token is that record's current token. Any
other token fails with `BadToken` and changes nothing. A record persists until
released or collected, so renewal is permitted on any existing record whose
token matches.

**B6 (deadline arithmetic).** Deadline computation is exact over the clock's
full range. A duration whose deadline cannot be represented is refused with
`TtlOverflow`; it is never folded, wrapped, or clamped into a deadline in the
past.

**B7 (revocation notice).** A lease counts as collected only once its holder
has been told. If a revocation notice cannot be delivered, `reap` reports the
failure to its caller rather than counting the lease as cleanly collected.

**B8 (bounded state).** Ending a lease frees everything the manager was holding
for that resource, including registered waiters. Retained state is bounded by
the number of live leases plus the number of waiters registered for resources
that still exist. No path accumulates per-resource state for resources that
have no lease.

## Non-goals

- Persistence. All state is in memory and is lost when the manager drops.
- Fair queueing. `register_waiter` records interest; it does not order grants.
- Clock validation. A caller that supplies a `now_ms` moving backwards gets
  undefined lease lifetimes, and that is its own fault.
- Notification retry or delivery ordering. A `Notifier` either reports success
  or reports failure, and `leasedb` does not retry on its behalf.
