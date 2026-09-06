"""
The project's concurrency primitives, in one place.

Three strategies cover every shared-state write in this codebase. They are not
interchangeable, and picking the wrong one is how the bugs below happened, so
this module names each with the situation it belongs to.


1. Conditional UPDATE -- "claim"
   ----------------------------
   For status transitions and one-shot operations: cancelling a boost,
   activating a mandate, paying a reward.

       claimed = Model.objects.filter(pk=pk, status='active').update(status='cancelled')
       if not claimed:
           ...someone else got there first

   A single UPDATE. PostgreSQL serialises concurrent UPDATEs against the same
   row, so exactly one of two racing callers finds the row still in the
   expected state; the loser gets 0 and stops. No transaction to hold open, no
   lock to release, and safe to leave an external network call outside it.

   ``claim_transition`` below is this pattern, named.


2. Row lock and re-read -- ``select_for_update``
   ---------------------------------------------
   For balances, where the new value depends on the current one and the
   decision to proceed depends on it too.

   The lock alone is not the point; re-reading under it is. A caller that locks
   the row and then trusts the copy it read *before* locking has gained
   nothing. UserCoinBalance.spend_coins and UserProfile._apply_delta both do
   this correctly and are the only places that should touch a balance.


3. Atomic in-place update -- ``F()``
   ---------------------------------
   For counters nobody reads before writing: votes, shares, view_count,
   total_entries.

       Model.objects.filter(pk=pk).update(votes=F('votes') + 1)

   Cheaper than a lock and immune to lost updates. It cannot express "fail if
   this would go negative" -- that needs strategy 2.


Why `obj.field += n; obj.save()` is never any of these
------------------------------------------------------
It reads in one statement and writes in another, so two callers both read the
old value and one increment vanishes. Worse, a bare ``save()`` writes *every*
column from a snapshot taken before the other request committed, so an
unrelated concurrent update to the same row is silently reverted -- an unlike
could roll back a share that landed between the read and the write.
"""

from django.db import transaction


def claim_transition(model, pk, *, field='status', expect, to, **extra_updates):
    """Move a row from one state to another, exactly once.

    Returns True for the caller that performed the transition and False for
    every other, including a retry of the same request. ``expect`` may be a
    single value or a collection of acceptable starting states.

    ``extra_updates`` are applied in the same UPDATE, so fields that must move
    together with the status -- a cancellation timestamp, a zeroed balance --
    cannot be left behind by a crash between two statements.

    Use this for anything that must happen once: refunds, payouts, activations,
    webhook processing. Check the return value; ignoring it reintroduces the
    double-execution this exists to prevent.
    """
    if isinstance(expect, list | tuple | set | frozenset):
        criteria = {f'{field}__in': list(expect)}
    else:
        criteria = {field: expect}

    updated = model.objects.filter(pk=pk, **criteria).update(**{field: to}, **extra_updates)
    return updated > 0


def locked(model, pk):
    """Fetch a row locked for update. Call inside ``transaction.atomic()``.

    The returned instance is the one to read and write -- not the copy the
    caller was already holding, which is exactly as stale as it was before the
    lock was taken.
    """
    return model.objects.select_for_update().get(pk=pk)


class LockedUpdate:
    """Lock a row, hand it back, save the fields that changed.

    A small wrapper so the read-under-lock and the narrow save stay together::

        with LockedUpdate(BoostCampaign, pk) as campaign:
            campaign.coins_remaining -= spend

    Saves only the attributes assigned inside the block, so a concurrent write
    to another column of the same row survives.
    """

    def __init__(self, model, pk):
        self._model = model
        self._pk = pk
        self._atomic = None
        self._instance = None
        self._before = None

    def __enter__(self):
        self._atomic = transaction.atomic()
        self._atomic.__enter__()
        self._instance = locked(self._model, self._pk)
        self._before = {
            f.attname: getattr(self._instance, f.attname) for f in self._model._meta.concrete_fields
        }
        return self._instance

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            changed = [
                name for name, was in self._before.items() if getattr(self._instance, name) != was
            ]
            if changed:
                self._instance.save(update_fields=changed)
        return self._atomic.__exit__(exc_type, exc, tb)


__all__ = ['LockedUpdate', 'claim_transition', 'locked']
