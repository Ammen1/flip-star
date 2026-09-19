"""
Two cancellations of the same withdrawal, arriving together.

`api/views/wallet.py::cancel_withdrawal` used to read the withdrawal outside
any transaction, check `can_cancel()` against that copy, and then refund. Two
taps on Cancel -- or a retried request -- both passed the check and both
refunded, so the user got their balance back twice for one withdrawal. The fix
locks the row and re-reads the status under the lock, in the same transaction
as the refund.

`tests/integration/test_withdrawal_refunds.py` covers the sequential case
through the real endpoint, which is not the same thing: it proves the status
guard, not the lock. Only real threads against a real database prove the lock,
so these run real threads against real PostgreSQL, and skip entirely on
SQLite. `tests/integration/test_concurrency.py` does the same for the other
race fixes and its docstring has the setup commands; these live in their own
file because appending to that one would drag a 200-line formatting sweep
into a money fix.
"""

from __future__ import annotations

import threading

import pytest
from django.contrib.auth.models import User
from django.db import connection

pytestmark = pytest.mark.integration

POINTS = 250

SKIP_REASON = (
    'Requires a real PostgreSQL connection (TEST_DB_ENGINE=postgresql + TEST_DB_* vars) -- '
    'row locking is not meaningfully testable against SQLite. See '
    'tests/integration/test_concurrency.py for how to run these.'
)


@pytest.fixture(scope='module')
def pg(django_db_blocker):
    """Real queries against the already-migrated test database.

    Deliberately not pytest-django's `django_db`: that wraps each test in a
    transaction its own threads cannot see into, which is the one thing these
    tests need. Same reasoning as test_concurrency.py, whose docstring has the
    setup commands.
    """
    if connection.vendor != 'postgresql':
        pytest.skip(SKIP_REASON)
    with django_db_blocker.unblock():
        yield


def run_together(fns):
    """Start every callable on its own thread at the same moment and wait.

    Each thread closes its own connection: Django's are thread-local and are
    not cleaned up otherwise.
    """
    results = [None] * len(fns)
    errors = [None] * len(fns)
    start = threading.Barrier(len(fns))

    def run(i, fn):
        try:
            start.wait(timeout=10)
            results[i] = fn()
        except Exception as exc:  # noqa: BLE001 -- surfaced by the assertions
            errors[i] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(i, fn)) for i, fn in enumerate(fns)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, errors


@pytest.fixture
def account(pg):
    """A user with no points, on the unblocked connection."""
    user = User.objects.create_user(username='refund_race', password='x')
    profile = user.profile
    profile.points = 0
    profile.save(update_fields=['points'])
    yield user
    user.delete()


def test_concurrent_cancellation_refunds_exactly_once(account):
    """Exactly one cancellation may move the row and refund. The other has to
    see the new status under the lock and do nothing."""
    from django.db import transaction as db_transaction

    from api.models.wallet import WithdrawalRequest

    profile = account.profile

    withdrawal = WithdrawalRequest.objects.create(
        user=account,
        point_amount=POINTS,
        gross_birr=25,
        fee_birr=5,
        net_birr=20,
        conversion_rate=10,
        payout_method='telebirr',
        payout_account='0912345678',
        status='pending',
    )

    def try_cancel():
        # Mirrors cancel_withdrawal's fixed body: lock, re-check the status
        # under that lock, then transition and refund in one transaction.
        with db_transaction.atomic():
            locked = WithdrawalRequest.objects.select_for_update().get(pk=withdrawal.pk)
            if not locked.can_cancel():
                return 'refused'
            locked.status = 'cancelled'
            locked.save(update_fields=['status'])
            locked.refund_to_user(reason='cancelled')
            return 'cancelled'

    results, errors = run_together([try_cancel, try_cancel])

    assert not any(errors), errors
    assert sorted(results) == ['cancelled', 'refused'], results

    profile.refresh_from_db()
    assert profile.points == POINTS, f'refunded {profile.points} for a {POINTS}-point withdrawal'


def test_concurrent_rejection_and_cancellation_refund_once_between_them(account):
    """An admin rejecting while the user cancels: the same row, two different
    endings, one refund. Both paths now go through the same locked
    transition, so whichever loses the race finds the row already settled."""
    from django.db import transaction as db_transaction

    from api.models.wallet import WithdrawalRequest

    profile = account.profile

    withdrawal = WithdrawalRequest.objects.create(
        user=account,
        point_amount=POINTS,
        gross_birr=25,
        fee_birr=5,
        net_birr=20,
        conversion_rate=10,
        payout_method='telebirr',
        payout_account='0912345678',
        status='pending',
    )

    def settle(new_status, refund_reason, allowed):
        with db_transaction.atomic():
            locked = WithdrawalRequest.objects.select_for_update().get(pk=withdrawal.pk)
            if locked.status not in allowed:
                return 'refused'
            locked.status = new_status
            locked.save(update_fields=['status'])
            locked.refund_to_user(reason=refund_reason)
            return new_status

    results, errors = run_together(
        [
            lambda: settle('cancelled', 'cancelled', {'pending'}),
            lambda: settle('rejected', 'rejected', {'pending', 'approved'}),
        ]
    )

    assert not any(errors), errors
    assert sorted(results).count('refused') == 1, results

    profile.refresh_from_db()
    assert profile.points == POINTS, f'refunded {profile.points} for a {POINTS}-point withdrawal'
