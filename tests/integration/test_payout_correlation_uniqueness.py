"""Audit H-04: the payout correlation key is unique in the database, not by habit.

A Telebirr result callback finds the row it settles by
``originator_conversation_id`` and resolves it with ``.first()``. If two rows can
share a key, one callback settles an arbitrary one of them -- on the path that
decides whether a user was paid.

These tests assert the database refuses the duplicate, which is the only place
the guarantee actually lives; an id generator that happens to produce unique
values is not a constraint.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from api.models.direct_debit import B2CPaymentTransaction, DirectDebitMandate
from api.models.wallet import WithdrawalRequest

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

OCID = 'S_X20260927DUPLICATE01'


@pytest.fixture
def payer(db):
    return User.objects.create_user(username='h04_payer', password='123456')  # noqa: S106


def _withdrawal(user, ocid):
    return WithdrawalRequest.objects.create(
        user=user,
        coin_amount=100,
        gross_birr=Decimal('10.00'),
        fee_birr=Decimal('0.00'),
        net_birr=Decimal('10.00'),
        conversion_rate=10,
        payout_account='251911223344',
        originator_conversation_id=ocid,
    )


def _b2c(user, ocid):
    return B2CPaymentTransaction.objects.create(
        payer=user,
        receiver_msisdn='251911223344',
        amount=Decimal('10.00'),
        originator_conversation_id=ocid,
    )


def _mandate(user, ocid):
    today = date.today()
    return DirectDebitMandate.objects.create(
        user=user,
        payer_msisdn='251911223344',
        payer_reference_number='REF-H04',
        payee_identifier_value='553559',
        frequency='05',  # Monthly; the column is varchar(2) with coded choices
        first_payment_date=today,
        expiry_date=today + timedelta(days=365),
        originator_conversation_id=ocid,
    )


# ── the duplicate is refused ─────────────────────────────────────────────────


def test_two_withdrawals_cannot_share_a_correlation_id(payer):
    _withdrawal(payer, OCID)
    with pytest.raises(IntegrityError), transaction.atomic():
        _withdrawal(payer, OCID)


def test_two_b2c_payments_cannot_share_a_correlation_id(payer):
    _b2c(payer, OCID)
    with pytest.raises(IntegrityError), transaction.atomic():
        _b2c(payer, OCID)


def test_two_mandates_cannot_share_a_correlation_id(payer):
    """N-02: the same defect on a third model, found while verifying H-04."""
    _mandate(payer, OCID)
    with pytest.raises(IntegrityError), transaction.atomic():
        _mandate(payer, OCID)


# ── the partial condition is what makes it deployable ────────────────────────


def test_many_withdrawals_may_still_have_no_correlation_id_yet(payer):
    """blank=True: a withdrawal exists before its B2C call is made."""
    _withdrawal(payer, '')
    _withdrawal(payer, '')
    _withdrawal(payer, '')
    assert WithdrawalRequest.objects.filter(originator_conversation_id='').count() == 3


def test_many_b2c_rows_may_still_have_no_correlation_id_yet(payer):
    _b2c(payer, '')
    _b2c(payer, '')
    assert B2CPaymentTransaction.objects.filter(originator_conversation_id='').count() == 2


def test_many_mandates_may_still_have_no_correlation_id_yet(payer):
    _mandate(payer, '')
    _mandate(payer, '')
    assert DirectDebitMandate.objects.filter(originator_conversation_id='').count() == 2


# ── the constraint does not reach across models ──────────────────────────────


def test_the_same_key_on_different_models_is_allowed(payer):
    """A withdrawal and its B2C row legitimately share one id."""
    _withdrawal(payer, OCID)
    _b2c(payer, OCID)
    assert WithdrawalRequest.objects.filter(originator_conversation_id=OCID).count() == 1
    assert B2CPaymentTransaction.objects.filter(originator_conversation_id=OCID).count() == 1


def test_distinct_keys_are_unaffected(payer):
    _withdrawal(payer, OCID + 'A')
    _withdrawal(payer, OCID + 'B')
    assert WithdrawalRequest.objects.exclude(originator_conversation_id='').count() == 2


# ── the constraints are actually declared where they claim to be ─────────────


@pytest.mark.parametrize(
    ('model', 'name'),
    [
        (WithdrawalRequest, 'uniq_withdrawal_originator_conversation_id'),
        (B2CPaymentTransaction, 'uniq_b2c_originator_conversation_id'),
        (DirectDebitMandate, 'uniq_mandate_originator_conversation_id'),
    ],
)
def test_the_constraint_is_declared_and_partial(model, name):
    declared = {c.name: c for c in model._meta.constraints}
    assert name in declared, f'{model.__name__} lost its H-04 constraint'
    constraint = declared[name]
    assert constraint.condition is not None, (
        'the constraint must stay partial; without the condition it collides with '
        'every row that has no correlation id yet'
    )
