"""
Choosing a username somebody already has.

The customer was shown the database's own words. Both registration paths
ended in ``except Exception as e: return Response({'error': str(e)})``, so a
duplicate that reached the constraint came back as a Postgres violation --
table name, column name and all. Nothing in it told them to pick another
name, and it exposed the schema to do it.

Two faults, not one:

* **the message**, which is fixed by never returning an exception and by
  answering a duplicate with one sentence that says what to do;
* **the check**, which was ``exists()`` followed by ``create_user()``. Two
  requests can pass that check before either writes. The pre-check is kept
  because it makes the ordinary case a tidy 409, but the database constraint
  is what actually prevents duplicates -- so the race is handled where it
  surfaces, as the same 409 rather than as a failure.

Case is decided by what the rest of the codebase already does: organization
admin creation refuses a name differing only in case, and gift delivery
resolves recipients with ``username__iexact``. Allowing 'Ammen' beside
'ammen' would make that lookup match two rows and raise, so registration
matches the stricter rule.
"""

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from api.services.usernames import (
    USERNAME_TAKEN_CODE,
    USERNAME_TAKEN_MESSAGE,
    is_duplicate_username_error,
    is_taken,
    taken_payload,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def existing():
    return User.objects.create_user(username='ammen', password='x')


# ── 1. available ────────────────────────────────────────────────────────────


def test_an_unused_username_is_available(existing):
    assert is_taken('someone_else') is False


def test_a_blank_username_is_not_reported_as_taken():
    """Empty is a different complaint, and the caller makes it."""
    assert is_taken('') is False
    assert is_taken(None) is False


def test_an_account_does_not_block_its_own_name(existing):
    """For editing a profile: keeping your own username is not a collision."""
    assert is_taken('ammen', exclude_user_id=existing.pk) is False


# ── 2. already taken ────────────────────────────────────────────────────────


def test_an_existing_username_is_taken(existing):
    assert is_taken('ammen') is True


def test_the_message_says_what_to_do(existing):
    payload = taken_payload()

    assert payload['code'] == USERNAME_TAKEN_CODE
    assert payload['error'] == USERNAME_TAKEN_MESSAGE
    assert 'already in use' in payload['error']
    assert 'choose another' in payload['error'].lower()
    assert payload['field'] == 'username'


def test_the_message_exposes_nothing_about_the_database(existing):
    """What the customer used to be shown: 'duplicate key value violates
    unique constraint "auth_user_username_key"'."""
    text = taken_payload()['error'].lower()

    for leak in ('constraint', 'duplicate key', 'auth_user', 'psycopg', 'traceback', 'sqlite'):
        assert leak not in text, f'the message leaks {leak!r}'


# ── 3. case ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize('variant', ['Ammen', 'AMMEN', 'aMMeN', ' ammen ', 'ammen'])
def test_case_and_surrounding_space_do_not_make_a_new_name(existing, variant):
    assert is_taken(variant) is True


def test_a_genuinely_different_name_is_still_free(existing):
    assert is_taken('ammen2') is False
    assert is_taken('ammenx') is False


def test_the_case_rule_matches_gift_delivery(existing):
    """Gifts resolve a recipient with username__iexact and call .get(). If
    registration allowed a case-variant, that call would match two rows and
    raise MultipleObjectsReturned -- so this rule is not cosmetic."""
    User.objects.create_user(username='someone', password='x')

    # The rule refuses the variant, so the ambiguous state never exists.
    assert is_taken('SOMEONE') is True


# ── 4. concurrency ──────────────────────────────────────────────────────────


def test_the_database_refuses_a_duplicate_whatever_the_check_said(existing):
    """The pre-check cannot be relied on alone: this is what actually stops
    two requests that both passed it."""
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(username='ammen', password='x')


def test_a_constraint_violation_is_recognised_as_a_duplicate(existing):
    """What turns the race into a 409 instead of a leaked exception."""
    try:
        with transaction.atomic():
            User.objects.create_user(username='ammen', password='x')
    except IntegrityError as exc:
        assert is_duplicate_username_error(exc) is True
    else:
        pytest.fail('the database allowed a duplicate username')


def test_an_unrelated_error_is_not_mistaken_for_a_duplicate():
    """A false positive here would answer every failure with 'pick another
    username', which is worse than unhelpful -- it is wrong."""
    assert is_duplicate_username_error(ValueError('connection refused')) is False
    assert is_duplicate_username_error(IntegrityError('email already exists')) is False


def test_a_case_variant_is_refused_before_the_database_sees_it(existing):
    """The constraint is case-sensitive, so 'Ammen' would be accepted by the
    database. The application rule is what keeps the two from coexisting."""
    assert is_taken('Ammen') is True

    # Proof the database alone would not have stopped it.
    with transaction.atomic():
        created = User.objects.create_user(username='Ammen', password='x')
    assert created.pk, 'the constraint is case-sensitive, as expected'
    created.delete()
