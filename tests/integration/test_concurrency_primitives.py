"""
The concurrency primitives themselves, verified without concurrency.

Why this file exists alongside the threaded tests
-------------------------------------------------
The race tests in test_concurrency_engagement.py need PostgreSQL and skip
everywhere else, so on SQLite they assert nothing at all. But most of what
makes those fixes correct is not the threading -- it is the shape of the
operation: does a claim admit exactly one caller, does a second attempt return
False rather than silently succeeding, does an F() update leave the row where
arithmetic says it should.

Those properties are testable sequentially, they run on every database, and
they are what actually fails if someone rewrites `claim_transition` into a
read-check-write. Treat this file as the always-on guard and the threaded file
as the proof that the guard holds under real contention.
"""

import pytest
from django.contrib.auth.models import User
from django.db.models import F, Value
from django.db.models.functions import Greatest

from api.models import Reel, Vote
from api.services.concurrency import claim_transition, locked

pytestmark = pytest.mark.django_db


@pytest.fixture
def author():
    return User.objects.create_user(username='primitive_author', password='123456')


@pytest.fixture
def reel(author):
    return Reel.objects.create(user=author, caption='c', votes=0, shares=0)


# ---------------------------------------------------------------------------
# claim_transition
# ---------------------------------------------------------------------------


def test_a_claim_succeeds_from_the_expected_state(reel):
    assert claim_transition(Reel, reel.pk, field='processed', expect=False, to=True) is True

    reel.refresh_from_db()
    assert reel.processed is True


def test_a_second_claim_returns_false(reel):
    """
    The whole point.

    A retry -- a redelivered webhook, a double tap, a worker running twice --
    must be told it lost, not silently allowed to repeat the work.
    """
    claim_transition(Reel, reel.pk, field='processed', expect=False, to=True)

    assert claim_transition(Reel, reel.pk, field='processed', expect=False, to=True) is False


def test_a_claim_from_the_wrong_state_does_nothing(reel):
    """A cancel arriving for an already-cancelled campaign changes nothing."""
    Reel.objects.filter(pk=reel.pk).update(processing_failed=True)

    claimed = claim_transition(Reel, reel.pk, field='processing_failed', expect=False, to=True)

    assert claimed is False


def test_a_claim_accepts_a_set_of_starting_states(reel):
    """Some transitions are legal from more than one state."""
    assert claim_transition(Reel, reel.pk, field='processed', expect=[False, None], to=True) is True


def test_extra_updates_land_in_the_same_statement(reel):
    """
    Fields that must move with the status move atomically with it.

    Two statements would let a crash leave a cancelled campaign still holding
    its coins -- the exact shape of the double-refund this replaced.
    """
    claim_transition(
        Reel, reel.pk, field='processed', expect=False, to=True, processing_failed=True
    )

    reel.refresh_from_db()
    assert reel.processed is True
    assert reel.processing_failed is True


def test_extra_updates_do_not_apply_to_a_lost_claim(reel):
    """The loser must change nothing at all, not just the status field."""
    claim_transition(Reel, reel.pk, field='processed', expect=False, to=True)

    claim_transition(
        Reel, reel.pk, field='processed', expect=False, to=True, processing_failed=True
    )

    reel.refresh_from_db()
    assert reel.processing_failed is False, 'a lost claim still wrote a field'


def test_a_claim_on_a_missing_row_is_false(reel):
    pk = reel.pk
    reel.delete()

    assert claim_transition(Reel, pk, field='processed', expect=False, to=True) is False


# ---------------------------------------------------------------------------
# Atomic counter updates
# ---------------------------------------------------------------------------


def test_an_f_increment_does_not_depend_on_the_in_memory_copy(reel):
    """
    The property `+= 1` lacks.

    The stale instance below still believes votes is 0. An F() update is
    computed by the database from the current row, so the write is correct
    regardless of what the caller was holding.
    """
    Reel.objects.filter(pk=reel.pk).update(votes=7)

    Reel.objects.filter(pk=reel.pk).update(votes=F('votes') + 1)

    reel.refresh_from_db()
    assert reel.votes == 8


def test_a_floored_decrement_stops_at_zero(reel):
    """
    Unlike must not drive the count negative.

    A stray unlike against a count already at zero -- from a retry, or a vote
    row deleted by moderation -- should be a no-op, not a negative tally.
    """
    Reel.objects.filter(pk=reel.pk).update(votes=Greatest(F('votes') - 1, Value(0)))

    reel.refresh_from_db()
    assert reel.votes == 0


def test_a_narrow_update_leaves_other_columns_alone(reel):
    """
    Why the bare save() was the worse half of the unlike bug.

    save() writes every column from the instance's snapshot. This asserts the
    replacement touches only what it names.
    """
    Reel.objects.filter(pk=reel.pk).update(shares=5)

    Reel.objects.filter(pk=reel.pk).update(votes=F('votes') + 1)

    reel.refresh_from_db()
    assert reel.shares == 5, 'an unrelated column was overwritten'
    assert reel.votes == 1


def test_a_stale_instance_save_would_clobber(reel):
    """
    The bug, demonstrated rather than described.

    `stale` was read before the share landed. Saving it writes shares=0 back
    over the 5 that were committed in between -- which is what the old unlike
    did to any share that raced it.
    """
    stale = Reel.objects.get(pk=reel.pk)
    Reel.objects.filter(pk=reel.pk).update(shares=5)

    stale.votes = 1
    stale.save()

    reel.refresh_from_db()
    assert reel.shares == 0, 'expected the documented clobber'

    # And the fix: naming the field confines the write to it.
    Reel.objects.filter(pk=reel.pk).update(shares=5)
    stale.votes = 2
    stale.save(update_fields=['votes'])

    reel.refresh_from_db()
    assert reel.shares == 5
    assert reel.votes == 2


# ---------------------------------------------------------------------------
# get_or_create as the check-then-create replacement
# ---------------------------------------------------------------------------


def test_get_or_create_reports_which_call_created(reel, author):
    _, first = Vote.objects.get_or_create(user=author, reel=reel)
    _, second = Vote.objects.get_or_create(user=author, reel=reel)

    assert first is True
    assert second is False
    assert Vote.objects.filter(reel=reel).count() == 1


def test_the_unique_constraint_is_the_real_guarantee(reel, author):
    """
    get_or_create narrows the window; the constraint closes it.

    Under real concurrency both callers can still reach the INSERT, and it is
    the database that rejects the second. This fails if the constraint is ever
    dropped in favour of application checks.
    """
    from django.db import IntegrityError, transaction

    Vote.objects.create(user=author, reel=reel)

    with pytest.raises(IntegrityError), transaction.atomic():
        Vote.objects.create(user=author, reel=reel)


# ---------------------------------------------------------------------------
# locked()
# ---------------------------------------------------------------------------


def test_locked_returns_the_row(reel):
    """
    Shape only.

    Whether the lock actually blocks a second writer is a PostgreSQL property
    and is asserted in test_concurrency_engagement.py; SQLite has no row-level
    locking to exercise here.
    """
    from django.db import transaction

    with transaction.atomic():
        row = locked(Reel, reel.pk)

    assert row.pk == reel.pk
