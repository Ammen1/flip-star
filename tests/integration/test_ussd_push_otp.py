"""
The SMS code that has to be answered before a USSD Push is sent.

What these prove
----------------
That the push endpoints cannot reach Telebirr without a session verified
through the OTP endpoints, and that a verified session authorises exactly one
payment -- the one it was opened for -- exactly once.

The Telebirr service is mocked throughout. A test that reached a real gateway
would put a PIN prompt on somebody's handset, which is the very thing this
feature exists to prevent.

Reading the code under test
---------------------------
The OTP is never returned by the API, so these read it back out of the queued
SmsMessage, the way the subscriber reads it off their phone. That doubles as
proof the message really went through the existing SMS queue rather than some
second path invented for payments.
"""

import json
import re
from datetime import timedelta
from decimal import Decimal

import fakeredis
import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models.payment_verification import PaymentVerificationSession
from api.models.sms import SmsMessage
from api.services import payment_otp

pytestmark = pytest.mark.django_db

PHONE = '251911223344'
OTHER_PHONE = '251911998877'
COIN = PaymentVerificationSession.PURPOSE_COIN_PURCHASE
SUB = PaymentVerificationSession.PURPOSE_SUBSCRIPTION

PUSH_ACCEPTED = {
    'success': True,
    'originator_conversation_id': 'OCID-1',
    'response_code': '0',
    'message': 'accepted',
}


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_cache():
    """Throttles and the hourly send counter live in the cache."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def server_keys():
    from infrastructure.keys import key_manager, redis_store

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    yield key_manager.get_public_key()
    key_manager.reset()
    redis_store.reset_client()


@pytest.fixture
def call(server_keys):
    """POST a body to a view over the encrypted transport it requires."""
    from common.security.e2e_encryption import decrypt_payload, encrypt_payload, generate_keypair

    client_public, client_private = generate_keypair()

    def _call(view, path, body, user=None):
        envelope = encrypt_payload(
            body, receiver_public_key_b64=server_keys, sender_private_key_b64=client_private
        ).to_dict()
        request = APIRequestFactory().post(
            path,
            data=json.dumps(envelope),
            content_type='application/json',
            HTTP_X_CLIENT_PUBLIC_KEY=client_public,
        )
        if user is not None:
            force_authenticate(request, user=user)
        response = view(request)
        response.render()
        payload = json.loads(response.content)
        if isinstance(payload, dict) and 'encrypted' in payload:
            payload = json.loads(
                decrypt_payload(
                    payload['encrypted'],
                    payload['nonce'],
                    server_keys,
                    payload['checksum'],
                    client_private,
                )
            )
        return response.status_code, payload

    return _call


@pytest.fixture
def request_otp(call):
    from api.views.payment_verification import request_ussd_push_otp

    def _request(body, user=None):
        return call(request_ussd_push_otp, '/charging/ussd-push/request-otp/', body, user)

    return _request


@pytest.fixture
def verify_otp(call):
    from api.views.payment_verification import verify_ussd_push_otp

    def _verify(body, user=None):
        return call(verify_ussd_push_otp, '/charging/ussd-push/verify-otp/', body, user)

    return _verify


@pytest.fixture
def push_coins(call):
    from api.views.wallet import telebirr_ussd_purchase

    def _push(body, user):
        return call(telebirr_ussd_purchase, '/wallet/telebirrUssdPurchase/', body, user)

    return _push


@pytest.fixture
def push_subscription(call):
    from api.views.subscription import telebirr_ussd_subscription_initiate

    def _push(body, user=None):
        return call(
            telebirr_ussd_subscription_initiate,
            '/subscription/telebirr/ussd/initiate/',
            body,
            user,
        )

    return _push


@pytest.fixture
def subscriber():
    """Someone who may buy coins: phone on file and a live plan."""
    from api.models import SubscriptionTier
    from api.models.subscription import SubscriptionPlan

    u = User.objects.create_user(username='payer', password='x')
    u.profile.phone_number = PHONE
    u.profile.save(update_fields=['phone_number'])
    SubscriptionPlan.objects.create(
        user=u,
        tier=SubscriptionTier.objects.filter(duration_type='monthly').first(),
        status='active',
        start_date=timezone.now() - timedelta(days=1),
        end_date=timezone.now() + timedelta(days=30),
    )
    return u


@pytest.fixture
def package():
    from api.models.contest import CoinPackage

    pkg, _ = CoinPackage.objects.get_or_create(
        price_etb=Decimal('25'),
        defaults={'name': 'Starter', 'coin_amount': 250, 'bonus_coins': 25, 'is_active': True},
    )
    CoinPackage.objects.filter(pk=pkg.pk).update(is_active=True)
    pkg.refresh_from_db()
    return pkg


@pytest.fixture
def tier():
    from api.models import SubscriptionTier

    return SubscriptionTier.objects.filter(is_active=True).first()


def sent_code(recipient=PHONE):
    """The code as the subscriber reads it off their handset."""
    message = (
        SmsMessage.objects.filter(recipient=recipient, purpose='otp_payment_verification')
        .order_by('-created_at')
        .first()
    )
    assert message is not None, 'no payment verification SMS was queued'
    match = re.search(r'\b(\d{6})\b', message.body)
    assert match, f'no code in the message: {message.body!r}'
    return match.group(1)


def telebirr(module):
    """Patch the Telebirr service a view calls, accepting the push."""
    from unittest.mock import patch

    return patch(f'api.views.{module}.telebirr_direct_debit_service')


def verified_coin_session(request_otp, verify_otp, subscriber, package):
    """Walk the real flow: request, read the SMS, verify. Returns the id."""
    _, body = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)
    session_id = body['session_id']
    status_code, _ = verify_otp(
        {'session_id': session_id, 'code': sent_code(), 'purpose': COIN}, subscriber
    )
    assert status_code == 200
    return session_id


# ---------------------------------------------------------------------------
# Requesting a code
# ---------------------------------------------------------------------------


def test_a_code_can_be_requested(request_otp, subscriber, package):
    status_code, body = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    assert status_code == 200
    assert body['success'] is True
    assert body['session_id']
    assert PaymentVerificationSession.objects.count() == 1


def test_the_code_goes_out_through_the_existing_sms_queue(request_otp, subscriber, package):
    request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    message = SmsMessage.objects.get()
    assert message.purpose == 'otp_payment_verification'
    assert message.recipient == PHONE
    assert 'payment code' in message.body
    assert 'Do not share' in message.body


def test_the_message_is_short_enough_for_the_gateway(request_otp, subscriber, package):
    """TIMWE refuse longer messages than the SMS standard does.

    The first version of this text was 99 characters -- a single GSM-7
    segment, nowhere near the 160 the spec permits -- and their SMPP gateway
    rejected every one with ESME_RINVMSGLEN while accepting a 92-character
    message over the same bind. Their real ceiling is below the standard's, so
    "one segment" is not a sufficient test for this message.

    90 is the ceiling asserted here: under the shortest length they have been
    observed to refuse, with room for a longer code or a changed expiry.
    """
    from api.services.sms.segments import is_gsm7, segments

    request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    body = SmsMessage.objects.get().body
    assert len(body) <= 90, f'{len(body)} characters: {body!r}'
    assert segments(body) == 1
    # A single non-GSM-7 character would switch the whole message to UCS-2,
    # where 90 characters really is two segments.
    assert is_gsm7(body), f'not GSM-7: {body!r}'


def test_the_message_still_says_what_it_is_for(request_otp, subscriber, package):
    """Short is not an excuse for a code that arrives unexplained."""
    request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    body = SmsMessage.objects.get().body
    assert 'FlipStar' in body
    assert 'payment' in body
    assert 'Do not share' in body
    assert '5 min' in body


def test_the_code_is_never_in_the_response(request_otp, subscriber, package):
    _, body = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    code = sent_code()
    assert code not in json.dumps(body)
    for value in body.values():
        assert str(value) != code


def test_the_code_is_never_stored_in_the_clear(request_otp, subscriber, package):
    request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    session = PaymentVerificationSession.objects.get()
    code = sent_code()
    assert session.otp_hash
    assert code not in session.otp_hash


def test_the_response_masks_the_number(request_otp, subscriber, package):
    _, body = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    assert body['phone_number'] != PHONE
    assert '****' in body['phone_number']


def test_a_coin_purchase_code_needs_a_signed_in_payer(request_otp, package):
    status_code, body = request_otp({'purpose': COIN, 'package_id': package.id})

    assert status_code == 401
    assert body['code'] == 'AUTHENTICATION_REQUIRED'
    assert not SmsMessage.objects.exists()


def test_a_subscriber_without_an_account_may_request_one(request_otp, tier):
    status_code, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': PHONE})

    assert status_code == 200
    assert body['success'] is True


# ---------------------------------------------------------------------------
# Verifying
# ---------------------------------------------------------------------------


def test_the_right_code_verifies(request_otp, verify_otp, subscriber, package):
    _, body = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    status_code, result = verify_otp(
        {'session_id': body['session_id'], 'code': sent_code(), 'purpose': COIN}, subscriber
    )

    assert status_code == 200
    assert result['verified'] is True
    session = PaymentVerificationSession.objects.get()
    assert session.status == PaymentVerificationSession.STATUS_VERIFIED


def test_the_wrong_code_does_not(request_otp, verify_otp, subscriber, package):
    _, body = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    status_code, result = verify_otp(
        {'session_id': body['session_id'], 'code': '000000', 'purpose': COIN}, subscriber
    )

    assert status_code == 400
    assert result['code'] == 'OTP_INVALID'
    assert result['attempts_remaining'] == payment_otp.MAX_ATTEMPTS - 1
    assert PaymentVerificationSession.objects.get().status == (
        PaymentVerificationSession.STATUS_PENDING
    )


def test_an_expired_code_does_not(request_otp, verify_otp, subscriber, package):
    _, body = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)
    code = sent_code()

    PaymentVerificationSession.objects.update(otp_expires_at=timezone.now() - timedelta(seconds=1))

    status_code, result = verify_otp(
        {'session_id': body['session_id'], 'code': code, 'purpose': COIN}, subscriber
    )

    assert status_code == 400
    assert result['code'] == 'OTP_EXPIRED'


def test_a_code_cannot_be_verified_twice(request_otp, verify_otp, subscriber, package):
    _, body = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)
    code = sent_code()
    verify_otp({'session_id': body['session_id'], 'code': code, 'purpose': COIN}, subscriber)

    status_code, result = verify_otp(
        {'session_id': body['session_id'], 'code': code, 'purpose': COIN}, subscriber
    )

    assert status_code == 400
    assert result['code'] == 'ALREADY_USED'


def test_a_code_for_one_number_cannot_verify_another(request_otp, verify_otp, subscriber, tier):
    # A session opened against PHONE, presented by somebody claiming OTHER.
    _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': PHONE})
    code = sent_code()

    status_code, result = verify_otp(
        {
            'session_id': body['session_id'],
            'code': code,
            'purpose': SUB,
            'phone_number': OTHER_PHONE,
        }
    )

    assert status_code == 400
    assert result['code'] == 'SESSION_MISMATCH'


def test_five_wrong_codes_end_the_session(request_otp, verify_otp, subscriber, package):
    _, body = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)
    session_id = body['session_id']

    for _ in range(payment_otp.MAX_ATTEMPTS):
        status_code, result = verify_otp(
            {'session_id': session_id, 'code': '000000', 'purpose': COIN}, subscriber
        )

    assert result['code'] == 'TOO_MANY_ATTEMPTS'
    assert PaymentVerificationSession.objects.get().status == (
        PaymentVerificationSession.STATUS_BLOCKED
    )

    # And the real code no longer helps.
    status_code, result = verify_otp(
        {'session_id': session_id, 'code': sent_code(), 'purpose': COIN}, subscriber
    )
    assert status_code == 400
    assert result['code'] == 'TOO_MANY_ATTEMPTS'


def test_a_failed_attempt_is_actually_recorded(request_otp, verify_otp, subscriber, package):
    """The count has to survive the rejection it caused.

    Incrementing inside the transaction and then raising from inside it rolls
    the increment straight back, leaving a counter that always reads zero: an
    attacker gets unlimited guesses behind a limit that looks enforced. Only a
    stored count makes the ceiling real, so it is asserted against the row
    rather than the response.
    """
    _, body = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    verify_otp({'session_id': body['session_id'], 'code': '000000', 'purpose': COIN}, subscriber)

    assert PaymentVerificationSession.objects.get().attempts == 1

    verify_otp({'session_id': body['session_id'], 'code': '111111', 'purpose': COIN}, subscriber)

    assert PaymentVerificationSession.objects.get().attempts == 2


def test_an_unknown_session_is_refused(verify_otp, subscriber):
    status_code, result = verify_otp(
        {'session_id': '11111111-2222-3333-4444-555555555555', 'code': '123456', 'purpose': COIN},
        subscriber,
    )

    assert status_code == 400
    assert result['code'] == 'SESSION_NOT_FOUND'


def test_a_malformed_session_id_does_not_raise(verify_otp, subscriber):
    status_code, result = verify_otp(
        {'session_id': 'not-a-uuid', 'code': '123456', 'purpose': COIN}, subscriber
    )

    assert status_code == 400
    assert result['code'] == 'SESSION_NOT_FOUND'


# ---------------------------------------------------------------------------
# Resending and rate limits
# ---------------------------------------------------------------------------


def test_a_resend_waits_for_the_cooldown(request_otp, subscriber, package):
    _, body = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    status_code, result = request_otp(
        {'purpose': COIN, 'package_id': package.id, 'session_id': body['session_id']}, subscriber
    )

    assert status_code == 429
    assert result['code'] == 'RESEND_COOLDOWN'
    assert result['retry_after'] > 0
    assert SmsMessage.objects.count() == 1, 'a second SMS went out during the cooldown'


def test_a_resend_after_the_cooldown_sends_a_new_code(request_otp, subscriber, package):
    _, body = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)
    first = sent_code()

    PaymentVerificationSession.objects.update(
        last_sent_at=timezone.now() - timedelta(seconds=payment_otp.RESEND_COOLDOWN_SECONDS + 1)
    )
    status_code, _ = request_otp(
        {'purpose': COIN, 'package_id': package.id, 'session_id': body['session_id']}, subscriber
    )

    assert status_code == 200
    assert SmsMessage.objects.count() == 2
    # A resend replaces the code; the old one must not still work.
    session = PaymentVerificationSession.objects.get()
    from django.contrib.auth.hashers import check_password

    assert not check_password(first, session.otp_hash)


def test_the_hourly_ceiling_stops_sending(request_otp, subscriber, package):
    for _ in range(payment_otp.MAX_SENDS_PER_PHONE_PER_HOUR):
        payment_otp._count_send(PHONE)

    status_code, result = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    assert status_code == 429
    assert result['code'] == 'HOURLY_LIMIT'
    assert not SmsMessage.objects.exists(), 'an SMS went out past the hourly ceiling'


def test_a_refused_request_sends_no_sms(request_otp, subscriber, package):
    for _ in range(payment_otp.MAX_SENDS_PER_PHONE_PER_HOUR):
        payment_otp._count_send(PHONE)

    request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    assert SmsMessage.objects.count() == 0


# ---------------------------------------------------------------------------
# SMS failure
# ---------------------------------------------------------------------------


def test_an_sms_that_cannot_be_queued_is_an_error(request_otp, subscriber, package):
    from unittest.mock import patch

    from api.services.sms.dispatch import SmsNotQueued

    with patch('api.services.sms.dispatch.queue_sms', side_effect=SmsNotQueued('gateway down')):
        status_code, result = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    assert status_code == 502
    assert result['code'] == 'SMS_FAILED'


def test_an_sms_failure_leaves_no_usable_session(request_otp, subscriber, package):
    from unittest.mock import patch

    from api.services.sms.dispatch import SmsNotQueued

    with patch('api.services.sms.dispatch.queue_sms', side_effect=SmsNotQueued('gateway down')):
        request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    assert not PaymentVerificationSession.objects.exists()


def test_an_sms_failure_stops_the_payment(request_otp, push_coins, subscriber, package):
    from unittest.mock import patch

    from api.services.sms.dispatch import SmsNotQueued

    with patch('api.services.sms.dispatch.queue_sms', side_effect=SmsNotQueued('gateway down')):
        _, body = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    with telebirr('wallet') as service:
        status_code, _ = push_coins(
            {'package_id': package.id, 'verification_session_id': body.get('session_id')},
            subscriber,
        )

    assert status_code == 403
    service.initiate_ussd_push_payment.assert_not_called()


# ---------------------------------------------------------------------------
# The push itself: nothing reaches Telebirr unverified
# ---------------------------------------------------------------------------


def test_a_push_without_any_verification_is_refused(push_coins, subscriber, package):
    with telebirr('wallet') as service:
        status_code, body = push_coins({'package_id': package.id}, subscriber)

    assert status_code == 403
    assert body['code'] == 'VERIFICATION_REQUIRED'
    service.initiate_ussd_push_payment.assert_not_called()


def test_a_push_on_an_unverified_session_is_refused(request_otp, push_coins, subscriber, package):
    _, body = request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    with telebirr('wallet') as service:
        status_code, result = push_coins(
            {'package_id': package.id, 'verification_session_id': body['session_id']}, subscriber
        )

    assert status_code == 403
    assert result['code'] == 'VERIFICATION_REQUIRED'
    service.initiate_ussd_push_payment.assert_not_called()


def test_a_verified_session_starts_the_push(
    request_otp, verify_otp, push_coins, subscriber, package
):
    session_id = verified_coin_session(request_otp, verify_otp, subscriber, package)

    with telebirr('wallet') as service:
        service.initiate_ussd_push_payment.return_value = PUSH_ACCEPTED
        status_code, body = push_coins(
            {'package_id': package.id, 'verification_session_id': session_id}, subscriber
        )

    assert status_code == 200
    assert body['success'] is True
    service.initiate_ussd_push_payment.assert_called_once()
    # The existing flow is untouched: same arguments as before this feature.
    kwargs = service.initiate_ussd_push_payment.call_args.kwargs
    assert kwargs['phone_number'] == PHONE
    assert kwargs['amount'] == f'{float(package.price_etb):.2f}'
    assert kwargs['coins'] == package.get_total_coins()


def test_a_verified_session_cannot_start_a_second_push(
    request_otp, verify_otp, push_coins, subscriber, package
):
    session_id = verified_coin_session(request_otp, verify_otp, subscriber, package)

    with telebirr('wallet') as service:
        service.initiate_ussd_push_payment.return_value = PUSH_ACCEPTED
        push_coins({'package_id': package.id, 'verification_session_id': session_id}, subscriber)

    # The successful push leaves a pending row, and the duplicate guard would
    # refuse the retry on its own. Clearing it leaves the spent verification
    # as the only thing that can refuse -- which is what this is about.
    from api.models.contest import CoinTransaction

    CoinTransaction.objects.all().delete()

    with telebirr('wallet') as second:
        status_code, body = push_coins(
            {'package_id': package.id, 'verification_session_id': session_id}, subscriber
        )

    assert status_code == 403
    assert body['code'] == 'VERIFICATION_ALREADY_USED'
    second.initiate_ussd_push_payment.assert_not_called()


def test_a_verified_session_expires(request_otp, verify_otp, push_coins, subscriber, package):
    session_id = verified_coin_session(request_otp, verify_otp, subscriber, package)
    PaymentVerificationSession.objects.update(
        session_expires_at=timezone.now() - timedelta(seconds=1)
    )

    with telebirr('wallet') as service:
        status_code, body = push_coins(
            {'package_id': package.id, 'verification_session_id': session_id}, subscriber
        )

    assert status_code == 403
    assert body['code'] == 'VERIFICATION_EXPIRED'
    service.initiate_ussd_push_payment.assert_not_called()


def test_a_refusal_that_is_not_about_the_code_keeps_the_verification(
    request_otp, verify_otp, push_coins, subscriber, package
):
    """A duplicate is refused without spending the verification.

    The check is placed after the duplicate guard for exactly this reason: a
    purchase that was going to be refused anyway must not cost the payer the
    code they already typed, and send them back for another one.
    """
    # A first push goes through and leaves a pending row.
    first = verified_coin_session(request_otp, verify_otp, subscriber, package)
    with telebirr('wallet') as service:
        service.initiate_ussd_push_payment.return_value = PUSH_ACCEPTED
        push_coins({'package_id': package.id, 'verification_session_id': first}, subscriber)

    # The payer, seeing nothing happen, verifies again and tries again.
    second = verified_coin_session(request_otp, verify_otp, subscriber, package)

    with telebirr('wallet') as service:
        status_code, _ = push_coins(
            {'package_id': package.id, 'verification_session_id': second}, subscriber
        )

    assert status_code == 409, 'the duplicate guard no longer runs first'
    service.initiate_ussd_push_payment.assert_not_called()
    still_good = PaymentVerificationSession.objects.get(id=second)
    assert (
        still_good.status == PaymentVerificationSession.STATUS_VERIFIED
    ), 'the verification was spent on a refusal that was not about the code'


def test_the_subscription_push_needs_verification_too(push_subscription, tier):
    with telebirr('subscription') as service:
        status_code, body = push_subscription({'tier_id': tier.id, 'phone_number': PHONE})

    assert status_code == 403
    assert body['code'] == 'VERIFICATION_REQUIRED'
    service.initiate_ussd_push_payment.assert_not_called()


def test_a_verified_subscription_session_starts_the_push(
    request_otp, verify_otp, push_subscription, tier
):
    _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': PHONE})
    verify_otp(
        {
            'session_id': body['session_id'],
            'code': sent_code(),
            'purpose': SUB,
            'phone_number': PHONE,
        }
    )

    with telebirr('subscription') as service:
        service.initiate_ussd_push_payment.return_value = PUSH_ACCEPTED
        status_code, result = push_subscription(
            {
                'tier_id': tier.id,
                'phone_number': PHONE,
                'verification_session_id': body['session_id'],
            }
        )

    assert status_code == 200
    assert result['success'] is True
    service.initiate_ussd_push_payment.assert_called_once()


# ---------------------------------------------------------------------------
# Bypass attempts
# ---------------------------------------------------------------------------


def test_claiming_otp_verified_authorises_nothing(push_coins, subscriber, package):
    """The frontend cannot assert its own verification."""
    with telebirr('wallet') as service:
        status_code, body = push_coins(
            {'package_id': package.id, 'otp_verified': True, 'verified': True}, subscriber
        )

    assert status_code == 403
    assert body['code'] == 'VERIFICATION_REQUIRED'
    service.initiate_ussd_push_payment.assert_not_called()


def test_a_session_for_one_package_cannot_buy_another(
    request_otp, verify_otp, push_coins, subscriber, package
):
    from api.models.contest import CoinPackage

    dearer = CoinPackage.objects.create(
        name='Bigger', price_etb=Decimal('100'), coin_amount=1000, bonus_coins=0, is_active=True
    )
    session_id = verified_coin_session(request_otp, verify_otp, subscriber, package)

    with telebirr('wallet') as service:
        status_code, body = push_coins(
            {'package_id': dearer.id, 'verification_session_id': session_id}, subscriber
        )

    assert status_code == 403
    assert body['code'] == 'VERIFICATION_MISMATCH'
    service.initiate_ussd_push_payment.assert_not_called()


def test_a_session_for_one_amount_cannot_pay_another(
    request_otp, verify_otp, push_coins, subscriber, package
):
    _, body = request_otp({'purpose': COIN, 'amount_etb': '25'}, subscriber)
    verify_otp({'session_id': body['session_id'], 'code': sent_code(), 'purpose': COIN}, subscriber)

    with telebirr('wallet') as service:
        status_code, result = push_coins(
            {'amount_etb': '250', 'verification_session_id': body['session_id']}, subscriber
        )

    assert status_code == 403
    assert result['code'] == 'VERIFICATION_MISMATCH'
    service.initiate_ussd_push_payment.assert_not_called()


def test_a_session_for_one_user_cannot_pay_for_another(
    request_otp, verify_otp, push_coins, subscriber, package
):
    # A profile's number is unique, so "same number, different account" cannot
    # arise here -- the two accounts differ on both, and the session is bound
    # to both.
    session_id = verified_coin_session(request_otp, verify_otp, subscriber, package)

    from api.models import SubscriptionTier
    from api.models.subscription import SubscriptionPlan

    other = User.objects.create_user(username='someone-else', password='x')
    other.profile.phone_number = OTHER_PHONE
    other.profile.save(update_fields=['phone_number'])
    SubscriptionPlan.objects.create(
        user=other,
        tier=SubscriptionTier.objects.filter(duration_type='monthly').first(),
        status='active',
        start_date=timezone.now() - timedelta(days=1),
        end_date=timezone.now() + timedelta(days=30),
    )

    with telebirr('wallet') as service:
        status_code, body = push_coins(
            {'package_id': package.id, 'verification_session_id': session_id}, other
        )

    assert status_code == 403
    service.initiate_ussd_push_payment.assert_not_called()


def test_a_session_for_one_tier_cannot_buy_another(request_otp, verify_otp, push_subscription):
    from api.models import SubscriptionTier

    tiers = list(SubscriptionTier.objects.filter(is_active=True)[:2])
    if len(tiers) < 2:
        pytest.skip('needs two active tiers')
    chosen, other = tiers

    _, body = request_otp({'purpose': SUB, 'tier_id': chosen.id, 'phone_number': PHONE})
    verify_otp(
        {
            'session_id': body['session_id'],
            'code': sent_code(),
            'purpose': SUB,
            'phone_number': PHONE,
        }
    )

    with telebirr('subscription') as service:
        status_code, result = push_subscription(
            {
                'tier_id': other.id,
                'phone_number': PHONE,
                'verification_session_id': body['session_id'],
            }
        )

    assert status_code == 403
    assert result['code'] == 'VERIFICATION_MISMATCH'
    service.initiate_ussd_push_payment.assert_not_called()


def test_a_coin_session_cannot_authorise_a_subscription(
    request_otp, verify_otp, push_subscription, subscriber, package, tier
):
    """Purposes do not cross, even for the same person and number."""
    session_id = verified_coin_session(request_otp, verify_otp, subscriber, package)

    # OTHER_PHONE so the already-subscribed guard is not what refuses it: the
    # point here is that the purpose does not cross, not that the payer has a
    # plan already.
    with telebirr('subscription') as service:
        status_code, body = push_subscription(
            {
                'tier_id': tier.id,
                'phone_number': OTHER_PHONE,
                'verification_session_id': session_id,
            }
        )

    assert status_code == 403
    assert body['code'] in ('VERIFICATION_MISMATCH', 'VERIFICATION_REQUIRED')
    service.initiate_ussd_push_payment.assert_not_called()


# ---------------------------------------------------------------------------
# Everything else stays as it was
# ---------------------------------------------------------------------------


def test_the_two_flows_resolve_the_same_number(subscriber):
    """The OTP endpoint must target the number the push will charge.

    If these ever disagree the code goes to one handset and the push to
    another, and every payment is refused on a fingerprint mismatch.
    """
    from api.views.payment_verification import phone_for_payment

    # Coin purchase: the profile's number, never the client's claim.
    assert phone_for_payment(user=subscriber, provided=OTHER_PHONE, purpose=COIN) == PHONE
    # Subscription: the client's number when given, the profile's otherwise.
    assert phone_for_payment(user=subscriber, provided=OTHER_PHONE, purpose=SUB) == OTHER_PHONE
    assert phone_for_payment(user=subscriber, provided=None, purpose=SUB) == PHONE


def test_the_superapp_flow_is_untouched():
    """The H5/SuperApp purchase does not go through USSD Push or this check."""
    import inspect

    from api.views import wallet

    source = inspect.getsource(wallet.telebirr_initiate_payment)
    assert 'verification_session_id' not in source
    assert 'consume_verified_session' not in source


def test_the_login_otp_service_is_untouched():
    """Registration and login codes keep their own service and behaviour."""
    from api.services.otp import OTPService

    assert OTPService.OTP_EXPIRY_MINUTES == 5
    assert OTPService.MAX_ATTEMPTS == 3
    assert hasattr(OTPService, 'send_otp')
    assert hasattr(OTPService, 'verify_otp')


def test_payment_codes_use_their_own_sms_purpose(request_otp, subscriber, package):
    """So a payment code is never mistaken for a login code in the logs."""
    request_otp({'purpose': COIN, 'package_id': package.id}, subscriber)

    assert SmsMessage.objects.filter(purpose='otp_payment_verification').count() == 1
    assert not SmsMessage.objects.filter(purpose__startswith='otp_login').exists()


def test_codes_come_from_a_csprng():
    """`random` is predictable from a few samples; a payment code must not be."""
    import inspect

    source = inspect.getsource(payment_otp.generate_code)
    assert 'secrets.' in source
    assert 'random.' not in source


def test_codes_are_six_digits_and_keep_leading_zeros():
    codes = {payment_otp.generate_code() for _ in range(200)}

    assert all(len(c) == 6 and c.isdigit() for c in codes)
    # 200 draws from a million should not collide; a constant would.
    assert len(codes) > 190
