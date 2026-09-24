"""
The messages a subscriber gets when money or access changes hands.

Three moments were silent until now, and each one is a moment the user cannot
see any other way:

* **STOP** -- they text the short code to cancel, and nothing came back. The
  only evidence the cancellation worked was a charge that failed to arrive.
* **a renewal** -- charged again, and told "you have successfully subscribed",
  with a fresh OTP that quietly invalidated the one they were using. It reads
  as a renewal now, and carries the same link as the first message: only that
  first one used to have it, so a subscriber who lost it was charged on with
  no way back in.
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


def test_the_first_message_carries_a_link(daily_tier, subscriber):
    _apply_relation(relation(), daily_tier, subscriber)

    assert 'subscription_tp=true' in only_message().body


def test_a_renewal_reads_as_a_renewal(daily_tier, subscriber):
    _apply_relation(relation(), daily_tier, subscriber)
    first = only_message()
    SmsMessage.objects.all().delete()

    # The MA charges the next period and notifies again.
    _apply_relation(relation(transaction_id='TX-2'), daily_tier, subscriber)

    sms = only_message()
    assert sms.purpose == 'subscription_renewal'
    assert 'renewed' in sms.body
    assert '3 ETB' in sms.body
    assert 'successfully subscribed' not in sms.body, 'a renewal is not a first subscription'
    assert first.body != sms.body


def test_a_renewal_carries_the_same_way_in_as_the_first_message(daily_tier, subscriber):
    """The reported gap: only the first message had a link. Somebody who lost
    it, or never got round to signing in, was charged month after month with
    no way back."""
    _apply_relation(relation(), daily_tier, subscriber)
    SmsMessage.objects.all().delete()

    _apply_relation(relation(transaction_id='TX-2'), daily_tier, subscriber)

    body = only_message().body
    assert 'subscription_tp=true' in body, 'a renewal offers no way in'
    assert MSISDN in body, 'the link does not carry their number'


def test_a_renewal_sends_the_code_because_the_charge_replaced_it(daily_tier, subscriber):
    """Why a renewal now carries an OTP, against the comment that used to say
    it must not: this path already replaces plan.setup_otp when it charges, so
    the code the subscriber was holding is dead either way. Saying nothing
    left them with a code that had silently stopped working."""
    _apply_relation(relation(), daily_tier, subscriber)
    plan = SubscriptionPlan.objects.get(onevas_phone_number=MSISDN)
    first_code = plan.setup_otp
    SmsMessage.objects.all().delete()

    _apply_relation(relation(transaction_id='TX-2'), daily_tier, subscriber)

    plan.refresh_from_db()
    assert plan.setup_otp != first_code, 'the stored code was not replaced after all'
    assert plan.setup_otp in only_message().body, 'the new code was never sent'


def test_a_renewal_we_charge_ourselves_keeps_their_code(daily_tier, subscriber):
    """The other renewal path does not touch the stored code, so it sends the
    link and no OTP -- issuing one there would break a working code."""
    from api.services import sms_subscription

    _apply_relation(relation(), daily_tier, subscriber)
    plan = SubscriptionPlan.objects.get(onevas_phone_number=MSISDN)

    body = sms_subscription.build_renewal_message(
        tier=daily_tier,
        plan=plan,
        phone_number=MSISDN,
        base_url='https://uat.flipstar.et/register',
    )

    assert 'subscription_tp=true' in body
    assert 'OTP' not in body
    assert plan.setup_otp not in body


def test_every_message_offers_the_same_link(daily_tier, subscriber):
    """One definition, so the three messages cannot drift apart again."""
    from api.services import sms_subscription

    link = sms_subscription.access_link(
        base_url='https://uat.flipstar.et/register', phone_number=MSISDN
    )

    assert link.startswith('https://uat.flipstar.et/register?subscription_tp=true')
    assert MSISDN in link
    assert 'existing_user' not in link

    with_account = sms_subscription.access_link(
        base_url='https://uat.flipstar.et/register', phone_number=MSISDN, existing_user=True
    )
    assert 'existing_user=true' in with_account, 'an account holder is sent to sign in'


# ── what a renewal costs to send ─────────────────────────────────────────────
#
# Adding the link pushed the renewal from 2 SMS segments to 3 -- a 50% rise in
# send cost on a message a daily subscriber receives every day. The wording was
# cut back to fit two, and these hold it there. Counted with
# api/services/sms/segments.py: GSM-7 bills 153 septets per part, and `len()`
# is not that number -- nine characters cost two septets, and a single
# non-GSM character would halve the capacity.


LINK_BASE = 'https://uat.flipstar.et/register'


def renewal_text(tier, plan, *, otp=None):
    from api.services import sms_subscription

    return sms_subscription.build_renewal_message(
        tier=tier, plan=plan, phone_number=MSISDN, base_url=LINK_BASE, otp=otp
    )


@pytest.mark.parametrize('duration', ['daily', 'weekly', 'monthly'])
def test_a_renewal_fits_two_segments_on_every_plan(subscriber, duration):
    """The longest plan renders around 250 septets against a 306 budget."""
    from api.services.sms.segments import describe, segments

    tier = SubscriptionTier.objects.get(duration_type=duration)
    plan = SubscriptionPlan.objects.create(
        user=subscriber,
        tier=tier,
        duration_type=duration,
        status='active',
        onevas_phone_number=MSISDN,
    )
    plan.activate()
    plan.refresh_from_db()

    with_code = renewal_text(tier, plan, otp='123456')
    without = renewal_text(tier, plan)

    assert segments(with_code) <= 2, f'{duration} with OTP: {describe(with_code)}'
    assert segments(without) <= 2, f'{duration} without OTP: {describe(without)}'


def test_the_longest_plausible_renewal_still_fits(subscriber):
    """The seeded plans are short-named. This is the shape that would bust the
    budget first: a long plan name, a four-figure price, and the longer of the
    two links (an account holder gets `existing_user=true` on the end)."""
    from api.services.sms.segments import describe, segments

    tier = SubscriptionTier.objects.create(
        name='Monthly Premium Plus',
        duration_type='monthly',
        duration_days=30,
        price_etb=1500,
        short_code='99999',
        is_active=True,
    )
    plan = SubscriptionPlan.objects.create(
        user=subscriber,
        tier=tier,
        duration_type='monthly',
        status='active',
        onevas_phone_number=MSISDN,
    )
    plan.activate()
    plan.refresh_from_db()

    body = renewal_text(tier, plan, otp='123456')

    assert 'existing_user=true' in body, 'not the longer link after all'
    assert segments(body) <= 2, describe(body)


def test_a_renewal_is_sent_as_gsm7(daily_tier, subscriber):
    """One non-GSM character -- a curly quote, an Amharic letter -- drops the
    capacity from 153 to 67 per part and would make this four segments."""
    from api.services.sms.segments import encoding_of

    _apply_relation(relation(), daily_tier, subscriber)
    plan = SubscriptionPlan.objects.get(onevas_phone_number=MSISDN)

    assert encoding_of(renewal_text(daily_tier, plan, otp='123456')) == 'GSM-7'


def test_the_renewal_still_says_everything_it_must(daily_tier, subscriber):
    """Shortened, not gutted: what was removed was the greeting and the
    padding around the link, never the facts."""
    _apply_relation(relation(), daily_tier, subscriber)
    plan = SubscriptionPlan.objects.get(onevas_phone_number=MSISDN)

    body = renewal_text(daily_tier, plan, otp='123456')

    assert 'Flipstar' in body
    assert daily_tier.name in body, 'which plan'
    assert f'{daily_tier.price_etb} ETB' in body, 'what it cost'
    assert 'valid until' in body, 'what it bought'
    assert 'subscription_tp=true' in body, 'the way in'
    assert '123456' in body, 'the code'
    assert 'STOP1' in body and str(daily_tier.short_code) in body, 'how to stop'
    assert 'Dear valued customer' not in body, 'the greeting was the first thing cut'


def test_the_first_subscription_message_is_unchanged(daily_tier, subscriber):
    """Only the renewal was shortened. The welcome message still reads as it
    did, greeting included."""
    _apply_relation(relation(), daily_tier, subscriber)

    body = only_message().body

    assert body.startswith('Dear valued customer, you have successfully subscribed')
    assert 'To access your premium service, please click on' in body
    assert 'and enter your OTP:' in body
    assert 'To cancel your subscription at any time, please send' in body


def test_the_stop_confirmation_is_unchanged(daily_tier, subscriber):
    """Untouched by this change."""
    from api.services import sms_subscription

    body = sms_subscription.build_cancellation_message(tier=daily_tier, subscribe_keyword='START1')

    assert body.startswith('Dear valued customer, your')
    assert 'has been cancelled and you will not be charged again' in body
    assert 'To subscribe again, send START1' in body
    assert 'Thank you for using Flipstar.' in body


def test_a_renewal_without_a_link_configured_still_reads_properly(daily_tier, subscriber):
    """No base URL means no link sentence -- not a broken one."""
    from api.services import sms_subscription

    _apply_relation(relation(), daily_tier, subscriber)
    plan = SubscriptionPlan.objects.get(onevas_phone_number=MSISDN)

    body = sms_subscription.build_renewal_message(tier=daily_tier, plan=plan)

    assert 'renewed' in body
    assert 'click on' not in body
    assert 'None' not in body


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


# ── the web app's address is configuration, and the link is well formed ────
#
# WEB_APP_LINK was a module constant carrying its own query string, including
# an unformatted "{masked_phone}" placeholder, and the resend-OTP caller
# appended a second query string to it. What went out was
#
#   .../register?subscription_tp=true&phone={masked_phone}?subscription_tp=true&token=...
#
# -- two '?', and a phone parameter whose value was the literal text
# "{masked_phone}". Anyone following it landed on a broken page. It also could
# not be pointed at another domain without editing Python.


def test_the_register_url_follows_the_configured_base():
    from django.test import override_settings

    from api.views.subscription import web_app_register_url

    with override_settings(WEB_APP_BASE_URL='https://flipstar.et'):
        assert web_app_register_url() == 'https://flipstar.et/register'


def test_a_trailing_slash_does_not_double_up():
    from django.test import override_settings

    from api.views.subscription import web_app_register_url

    with override_settings(WEB_APP_BASE_URL='https://flipstar.et/'):
        assert web_app_register_url() == 'https://flipstar.et/register'


def test_the_register_url_carries_no_query_string_of_its_own():
    """The caller owns the query string; two of them make a broken URL."""
    from api.views.subscription import web_app_register_url

    url = web_app_register_url()

    assert '?' not in url
    assert '{' not in url, 'an unformatted placeholder is still in the URL'
