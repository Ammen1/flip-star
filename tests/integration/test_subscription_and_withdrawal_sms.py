"""
The messages a subscriber gets when money or access changes hands.

Three moments were silent until now, and each one is a moment the user cannot
see any other way:

* **STOP** -- they text the short code to cancel, and nothing came back. The
  only evidence the cancellation worked was a charge that failed to arrive.
* **a renewal** -- charged again, and told "you have successfully subscribed",
  with a fresh OTP that quietly invalidated the one they were using.
* **a withdrawal** -- points handed over, money expected somewhere else, and
  no word at any stage: not when it was paid, not when it failed, not when
  the points came back.

What these tests hold down is mostly that the messages are *true*: that a
cancellation SMS is only sent when something was actually cancelled, that
"your points have been returned" is only said where they actually were, and
that a webhook arriving twice does not text somebody twice.

The gateway is never reached: queue_sms writes an SmsMessage row and hands the
rest to the SMS worker, so the rows are what these assert on.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User

from api.integrations.timwe.datasync import SyncOrderRelation
from api.models import SubscriptionPlan, SubscriptionTier
from api.models.sms import SmsMessage
from api.models.wallet import WithdrawalRequest
from api.services import withdrawal_sms
from api.views.timwe import _apply_relation

pytestmark = pytest.mark.django_db

MSISDN = '251912345678'


def relation(update_type=1, transaction_id='TX-1', msisdn=MSISDN, keyword=''):
    """One syncOrderRelation notification: 1 subscribe, 2 unsubscribe."""
    extensions = {'orderKey': 'OK-1'}
    if transaction_id:
        extensions['transactionID'] = transaction_id
    if keyword:
        extensions['keyword'] = keyword
    return SyncOrderRelation(
        user_id=msisdn,
        user_type=0,
        sp_id='300263',
        product_id='10000302850',
        service_id='30026300007331',
        update_type=update_type,
        update_time='20260916120000',
        extensions=extensions,
    )


def messages(purpose=None):
    rows = SmsMessage.objects.all()
    return list(rows.filter(purpose=purpose) if purpose else rows)


def only_message(purpose=None):
    rows = messages(purpose)
    assert len(rows) == 1, f'expected one SMS, found {[(r.purpose, r.body[:40]) for r in rows]}'
    return rows[0]


@pytest.fixture
def daily_tier():
    return SubscriptionTier.objects.create(
        name='Daily Premium',
        slug='daily-premium',
        duration_type='daily',
        duration_days=1,
        price_etb=3,
        short_code='9286',
        product_id='10000302850',
        onevas_code='TDAILY',
    )


@pytest.fixture
def subscriber():
    user = User.objects.create_user(username='subscriber', password='x')
    user.profile.phone_number = MSISDN
    user.profile.save(update_fields=['phone_number'])
    return user


# ── STOP ─────────────────────────────────────────────────────────────────────


def test_a_stop_is_confirmed_by_sms(daily_tier, subscriber):
    _apply_relation(relation(), daily_tier, subscriber)
    SmsMessage.objects.all().delete()  # the welcome message; this is about STOP

    applied, _ = _apply_relation(
        relation(update_type=2, transaction_id='TX-2'), daily_tier, subscriber
    )

    assert applied is True
    sms = only_message()
    assert sms.purpose == 'subscription_cancelled'
    assert sms.recipient == MSISDN
    assert 'cancelled' in sms.body
    assert 'Daily Premium' in sms.body
    assert 'not be charged again' in sms.body


def test_the_cancellation_sms_says_how_to_come_back(daily_tier, subscriber):
    _apply_relation(relation(), daily_tier, subscriber)
    SmsMessage.objects.all().delete()

    _apply_relation(relation(update_type=2, transaction_id='TX-2'), daily_tier, subscriber)

    body = only_message().body
    assert 'send 1 to 9286' in body, f'no way back in: {body}'


def test_nothing_cancelled_means_nothing_sent(daily_tier, subscriber):
    """The MA reports a cancellation we have already applied. Texting "you are
    cancelled" again is a message about our bookkeeping, not about them."""
    applied, _ = _apply_relation(relation(update_type=2), daily_tier, subscriber)

    assert applied is False
    assert messages() == []


def test_a_retried_stop_notification_does_not_text_twice(daily_tier, subscriber):
    _apply_relation(relation(), daily_tier, subscriber)
    SmsMessage.objects.all().delete()

    _apply_relation(relation(update_type=2, transaction_id='TX-SAME'), daily_tier, subscriber)
    # The MA retries anything it did not get a 0 for. Same event, same id.
    _apply_relation(relation(update_type=2, transaction_id='TX-SAME'), daily_tier, subscriber)

    assert len(messages()) == 1


def test_a_cancellation_stands_even_if_the_sms_cannot_be_sent(daily_tier, subscriber):
    """A non-zero answer makes the MA retry a cancellation already applied, so
    a gateway problem must not reach the response."""
    _apply_relation(relation(), daily_tier, subscriber)

    with patch(
        'api.services.sms_subscription.send_subscription_sms',
        side_effect=RuntimeError('gateway down'),
    ):
        applied, _ = _apply_relation(
            relation(update_type=2, transaction_id='TX-2'), daily_tier, subscriber
        )

    assert applied is True
    assert not SubscriptionPlan.objects.filter(user=subscriber, status='active').exists()


# ── subscribing and renewing ─────────────────────────────────────────────────


def test_the_first_charge_sends_the_welcome_message_with_the_way_in(daily_tier, subscriber):
    _apply_relation(relation(), daily_tier, subscriber)

    sms = only_message()
    assert sms.purpose == 'subscription_welcome'
    assert 'successfully subscribed' in sms.body
    assert 'OTP' in sms.body


def test_a_renewal_reads_as_a_renewal_and_keeps_the_old_otp(daily_tier, subscriber):
    _apply_relation(relation(), daily_tier, subscriber)
    first = only_message()
    SmsMessage.objects.all().delete()

    # The MA charges the next period and notifies again.
    _apply_relation(relation(transaction_id='TX-2'), daily_tier, subscriber)

    sms = only_message()
    assert sms.purpose == 'subscription_renewal'
    assert 'renewed' in sms.body
    assert '3 ETB' in sms.body
    assert 'OTP' not in sms.body, 'a renewal must not invalidate the code they are using'
    assert first.body != sms.body


# ── withdrawals ──────────────────────────────────────────────────────────────


@pytest.fixture
def withdrawal(subscriber):
    return WithdrawalRequest.objects.create(
        user=subscriber,
        point_amount=1000,
        gross_birr=Decimal('100.00'),
        fee_birr=Decimal('5.00'),
        net_birr=Decimal('95.00'),
        conversion_rate=10,
        payout_method='telebirr',
        payout_account='251911528271',
        status='processing',
    )


def test_a_paid_withdrawal_sends_the_receipt(withdrawal):
    withdrawal.payout_reference = 'TB123456789'

    assert withdrawal_sms.notify_paid(withdrawal) is True

    sms = only_message()
    assert sms.purpose == 'withdrawal_paid'
    assert sms.recipient == MSISDN
    assert '95 ETB' in sms.body, sms.body
    assert 'TB123456789' in sms.body, 'the reference is what they quote to telebirr'
    assert '251911528271' not in sms.body, 'the account is masked'


def test_a_failed_withdrawal_says_the_points_are_back_when_they_are(withdrawal):
    withdrawal_sms.notify_failed(withdrawal, refunded=True)

    body = only_message().body
    assert 'could not be completed' in body
    assert '1000 points have been returned' in body


def test_a_failed_withdrawal_does_not_promise_a_refund_that_did_not_happen(withdrawal):
    """Admin rejection of a points withdrawal refunds nothing today (its refund
    reads the legacy coin field). Saying otherwise would be a lie by SMS."""
    withdrawal_sms.notify_failed(withdrawal, refunded=False)

    body = only_message().body
    assert 'returned' not in body
    assert 'support' in body


def test_the_same_result_arriving_twice_texts_once(withdrawal):
    """Telebirr retries its webhook."""
    withdrawal_sms.notify_paid(withdrawal)
    withdrawal_sms.notify_paid(withdrawal)

    assert len(messages()) == 1


def test_paid_and_failed_are_separate_events(withdrawal):
    """A withdrawal that failed and was later paid by hand says both."""
    withdrawal_sms.notify_failed(withdrawal, refunded=True)
    withdrawal_sms.notify_paid(withdrawal)

    assert len(messages()) == 2


def test_a_withdrawal_with_no_number_anywhere_is_not_an_error(subscriber):
    subscriber.profile.phone_number = ''
    subscriber.profile.save(update_fields=['phone_number'])
    request = WithdrawalRequest.objects.create(
        user=subscriber,
        point_amount=500,
        gross_birr=Decimal('50.00'),
        fee_birr=Decimal('0.00'),
        net_birr=Decimal('50.00'),
        conversion_rate=10,
        payout_method='bank_transfer',
        payout_account='1000123456789',
        status='processing',
    )

    assert withdrawal_sms.notify_paid(request) is False
    assert messages() == []


def test_a_telebirr_payout_can_text_the_payout_number_itself(subscriber):
    """No number on the profile, but the payout account is one."""
    subscriber.profile.phone_number = ''
    subscriber.profile.save(update_fields=['phone_number'])
    request = WithdrawalRequest.objects.create(
        user=subscriber,
        point_amount=500,
        gross_birr=Decimal('50.00'),
        fee_birr=Decimal('0.00'),
        net_birr=Decimal('50.00'),
        conversion_rate=10,
        payout_method='telebirr',
        payout_account='251911528271',
        status='processing',
    )

    assert withdrawal_sms.notify_paid(request) is True
    assert only_message().recipient == '251911528271'


def test_a_gateway_problem_never_reaches_the_payout(withdrawal):
    with patch('api.services.sms.dispatch.queue_sms', side_effect=RuntimeError('gateway down')):
        assert withdrawal_sms.notify_paid(withdrawal) is False


def test_amounts_read_like_money(withdrawal):
    withdrawal.net_birr = Decimal('95.50')

    withdrawal_sms.notify_paid(withdrawal)

    assert '95.50 ETB' in only_message().body


def test_every_withdrawal_message_is_traceable_to_its_withdrawal(withdrawal):
    withdrawal_sms.notify_paid(withdrawal)

    assert only_message().idempotency_key == f'withdrawal:{withdrawal.id}:paid'


def test_two_withdrawals_are_not_confused_for_each_other(subscriber, withdrawal):
    second = WithdrawalRequest.objects.create(
        user=subscriber,
        point_amount=200,
        gross_birr=Decimal('20.00'),
        fee_birr=Decimal('0.00'),
        net_birr=Decimal('20.00'),
        conversion_rate=10,
        payout_method='telebirr',
        payout_account='251911528271',
        status='processing',
    )

    withdrawal_sms.notify_paid(withdrawal)
    withdrawal_sms.notify_paid(second)

    assert len(messages()) == 2
    assert {m.idempotency_key for m in messages()} == {
        f'withdrawal:{withdrawal.id}:paid',
        f'withdrawal:{second.id}:paid',
    }
