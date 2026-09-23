"""
The SMS code that has to be answered before a SUBSCRIPTION USSD Push is sent.

Which flows need this, and why
------------------------------
Subscribing does. That endpoint is reachable with no account at all -- a phone
number typed into a form is the only identity there is -- so without a check
anyone could raise a PIN prompt on any handset they cared to name, at a moment
of their choosing.

Buying coins does not. That buyer is already signed in, and
``telebirr_ussd_purchase`` ignores any number in the request body and charges
the one on their own profile. A code sent to that number proves something the
session already proved, so the only thing it adds is a step. The first half of
this file exists to keep it that way: coin purchases must not send a code,
must not ask for one, and must not regain a verification step by accident.

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

#: The coin buyer's number: an account exists, and it has a live plan.
PHONE = '251911223344'
#: The subscriber-to-be's number: no account, no plan.
SUB_PHONE = '251911998877'
OTHER_PHONE = '251911777666'
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
def push_coins(call):
    from api.views.wallet import telebirr_ussd_purchase

    def _push(body, user=None):
        return call(telebirr_ussd_purchase, '/wallet/telebirrUssdPurchase/', body, user)

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


def sent_code(recipient=SUB_PHONE):
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
    """Patch the Telebirr service a view calls."""
    from unittest.mock import patch

    return patch(f'api.views.{module}.telebirr_direct_debit_service')


def verified_session(request_otp, verify_otp, tier, phone=SUB_PHONE):
    """Walk the real flow: request, read the SMS, verify. Returns the id."""
    _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': phone})
    session_id = body['session_id']
    status_code, _ = verify_otp(
        {'session_id': session_id, 'code': sent_code(phone), 'phone_number': phone}
    )
    assert status_code == 200
    return session_id


# ===========================================================================
# Buying coins asks for nothing
# ===========================================================================


def test_a_coin_purchase_needs_no_verification(push_coins, subscriber, package):
    """The whole point of this change: signed in is enough."""
    with telebirr('wallet') as service:
        service.initiate_ussd_push_payment.return_value = PUSH_ACCEPTED
        status_code, body = push_coins({'package_id': package.id}, subscriber)

    assert status_code == 200
    assert body['success'] is True
    service.initiate_ussd_push_payment.assert_called_once()


def test_a_coin_purchase_sends_no_code(push_coins, subscriber, package):
    with telebirr('wallet') as service:
        service.initiate_ussd_push_payment.return_value = PUSH_ACCEPTED
        push_coins({'package_id': package.id}, subscriber)

    assert not SmsMessage.objects.exists(), 'a coin purchase queued an SMS'


def test_a_coin_purchase_opens_no_verification_session(push_coins, subscriber, package):
    with telebirr('wallet') as service:
        service.initiate_ussd_push_payment.return_value = PUSH_ACCEPTED
        push_coins({'package_id': package.id}, subscriber)

    assert not PaymentVerificationSession.objects.exists()


def test_the_coin_endpoint_has_no_verification_step_left():
    """Structural, so the call cannot creep back in unnoticed.

    A behavioural test alone would pass against a view that consulted a
    session and happened to find one; this asserts the code is not there.
    """
    import inspect

    from api.views import wallet

    source = inspect.getsource(wallet.telebirr_ussd_purchase)
    assert 'consume_verified_session' not in source
    assert 'verification_session_id' not in source
    assert 'payment_otp' not in source


def test_a_coin_purchase_ignores_a_verification_session_it_is_given(
    push_coins, subscriber, package
):
    """An old client sending the field is not an error, and buys nothing."""
    with telebirr('wallet') as service:
        service.initiate_ussd_push_payment.return_value = PUSH_ACCEPTED
        status_code, _ = push_coins(
            {'package_id': package.id, 'verification_session_id': 'anything-at-all'}, subscriber
        )

    assert status_code == 200
    service.initiate_ussd_push_payment.assert_called_once()


def test_a_signed_out_caller_still_cannot_buy_coins(push_coins, package):
    """Removing the code did not remove what was actually guarding it."""
    with telebirr('wallet') as service:
        status_code, _ = push_coins({'package_id': package.id})

    assert status_code in (401, 403)
    service.initiate_ussd_push_payment.assert_not_called()


def test_the_coin_duplicate_guard_still_refuses_a_second_push(push_coins, subscriber, package):
    """Idempotency is untouched by any of this."""
    with telebirr('wallet') as service:
        service.initiate_ussd_push_payment.return_value = PUSH_ACCEPTED
        push_coins({'package_id': package.id}, subscriber)

    with telebirr('wallet') as second:
        status_code, _ = push_coins({'package_id': package.id}, subscriber)

    assert status_code == 409
    second.initiate_ussd_push_payment.assert_not_called()


def test_a_coin_purchase_still_charges_the_right_amount(push_coins, subscriber, package):
    with telebirr('wallet') as service:
        service.initiate_ussd_push_payment.return_value = PUSH_ACCEPTED
        push_coins({'package_id': package.id}, subscriber)

    kwargs = service.initiate_ussd_push_payment.call_args.kwargs
    assert kwargs['amount'] == f'{float(package.price_etb):.2f}'
    assert kwargs['coins'] == package.get_total_coins()
    assert kwargs['phone_number'] == PHONE


def test_the_verification_endpoints_refuse_a_coin_purchase(request_otp, subscriber, package):
    """There is no coin purpose any more; asking for one is a 400."""
    status_code, body = request_otp(
        {'purpose': 'coin_purchase', 'package_id': package.id}, subscriber
    )

    assert status_code == 400
    assert body['code'] == 'INVALID_PURPOSE'
    assert not SmsMessage.objects.exists()


def test_subscription_is_the_only_purpose_there_is():
    """Pinned: adding one back is a decision, not a drive-by."""
    assert PaymentVerificationSession.PURPOSE_CHOICES == [('subscription', 'Subscription')]
    assert not hasattr(PaymentVerificationSession, 'PURPOSE_COIN_PURCHASE')


# ===========================================================================
# Subscribing still asks
# ===========================================================================


def test_a_code_can_be_requested(request_otp, tier):
    status_code, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})

    assert status_code == 200
    assert body['success'] is True
    assert body['session_id']


def test_a_tier_is_required(request_otp):
    status_code, body = request_otp({'purpose': SUB, 'phone_number': SUB_PHONE})

    assert status_code == 400
    assert body['code'] == 'TIER_REQUIRED'
    assert not SmsMessage.objects.exists()


def test_the_code_goes_out_through_the_existing_sms_queue(request_otp, tier):
    request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})

    message = SmsMessage.objects.get()
    assert message.purpose == 'otp_payment_verification'
    assert message.recipient == SUB_PHONE
    assert 'payment code' in message.body
    assert 'Do not share' in message.body


def test_the_message_is_short_enough_for_the_gateway(request_otp, tier):
    """TIMWE refuse longer messages than the SMS standard does.

    The first version of this text was 99 characters -- a single GSM-7
    segment, nowhere near the 160 the spec permits -- and their SMPP gateway
    rejected every one with ESME_RINVMSGLEN while accepting a 92-character
    message over the same bind. Their real ceiling is below the standard's, so
    "one segment" is not a sufficient test for this message.
    """
    from api.services.sms.segments import is_gsm7, segments

    request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})

    body = SmsMessage.objects.get().body
    assert len(body) <= 90, f'{len(body)} characters: {body!r}'
    assert segments(body) == 1
    assert is_gsm7(body), f'not GSM-7: {body!r}'


def test_the_message_still_says_what_it_is_for(request_otp, tier):
    request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})

    body = SmsMessage.objects.get().body
    assert 'FlipStar' in body
    assert 'payment' in body
    assert 'Do not share' in body
    assert '5 min' in body


def test_the_code_is_never_in_the_response(request_otp, tier):
    _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})

    assert sent_code() not in json.dumps(body)


def test_the_code_is_never_stored_in_the_clear(request_otp, tier):
    request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})

    session = PaymentVerificationSession.objects.get()
    assert session.otp_hash
    assert sent_code() not in session.otp_hash


def test_the_response_masks_the_number(request_otp, tier):
    _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})

    assert body['phone_number'] != SUB_PHONE
    assert '****' in body['phone_number']


def test_a_payer_without_an_account_may_request_one(request_otp, tier):
    """The case this whole feature exists for."""
    status_code, _ = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})

    assert status_code == 200
    assert PaymentVerificationSession.objects.get().user_id is None


# ---------------------------------------------------------------------------
# Verifying
# ---------------------------------------------------------------------------


def test_the_right_code_verifies(request_otp, verify_otp, tier):
    _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})

    status_code, result = verify_otp(
        {'session_id': body['session_id'], 'code': sent_code(), 'phone_number': SUB_PHONE}
    )

    assert status_code == 200
    assert result['verified'] is True
    assert PaymentVerificationSession.objects.get().status == (
        PaymentVerificationSession.STATUS_VERIFIED
    )


def test_the_wrong_code_does_not(request_otp, verify_otp, tier):
    _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})

    status_code, result = verify_otp(
        {'session_id': body['session_id'], 'code': '000000', 'phone_number': SUB_PHONE}
    )

    assert status_code == 400
    assert result['code'] == 'OTP_INVALID'
    assert result['attempts_remaining'] == payment_otp.MAX_ATTEMPTS - 1


def test_an_expired_code_does_not(request_otp, verify_otp, tier):
    _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})
    code = sent_code()
    PaymentVerificationSession.objects.update(otp_expires_at=timezone.now() - timedelta(seconds=1))

    status_code, result = verify_otp(
        {'session_id': body['session_id'], 'code': code, 'phone_number': SUB_PHONE}
    )

    assert status_code == 400
    assert result['code'] == 'OTP_EXPIRED'


def test_a_code_cannot_be_verified_twice(request_otp, verify_otp, tier):
    _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})
    code = sent_code()
    verify_otp({'session_id': body['session_id'], 'code': code, 'phone_number': SUB_PHONE})

    status_code, result = verify_otp(
        {'session_id': body['session_id'], 'code': code, 'phone_number': SUB_PHONE}
    )

    assert status_code == 400
    assert result['code'] == 'ALREADY_USED'


def test_a_code_for_one_number_cannot_verify_another(request_otp, verify_otp, tier):
    _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})
    code = sent_code()

    status_code, result = verify_otp(
        {'session_id': body['session_id'], 'code': code, 'phone_number': OTHER_PHONE}
    )

    assert status_code == 400
    assert result['code'] == 'SESSION_MISMATCH'


def test_five_wrong_codes_end_the_session(request_otp, verify_otp, tier):
    _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})
    session_id = body['session_id']

    for _ in range(payment_otp.MAX_ATTEMPTS):
        _, result = verify_otp(
            {'session_id': session_id, 'code': '000000', 'phone_number': SUB_PHONE}
        )

    assert result['code'] == 'TOO_MANY_ATTEMPTS'
    assert PaymentVerificationSession.objects.get().status == (
        PaymentVerificationSession.STATUS_BLOCKED
    )

    # Stand in for a minute passing, so the next call tests the session rather
    # than the request throttle.
    #
    # Those five attempts already exhaust the anonymous verify allowance.
    # common/throttling._make pairs an Anon and a User throttle on one scope,
    # and for an anonymous caller DRF's UserRateThrottle falls back to the
    # same identifier as the Anon one -- so both write the same cache key and
    # every request is counted twice. The configured otp_verify '10/min' is
    # therefore 5/min in practice for anyone without a token, which is exactly
    # MAX_ATTEMPTS. Strict rather than permissive, so not a hole, but it is
    # why a sixth call inside the same minute answers 429.
    cache.clear()

    status_code, result = verify_otp(
        {'session_id': session_id, 'code': sent_code(), 'phone_number': SUB_PHONE}
    )
    assert status_code == 400
    assert result['code'] == 'TOO_MANY_ATTEMPTS'


def test_a_failed_attempt_is_actually_recorded(request_otp, verify_otp, tier):
    """The count has to survive the rejection it caused.

    Incrementing inside the transaction and then raising from inside it rolls
    the increment straight back, leaving a counter that always reads zero: an
    attacker gets unlimited guesses behind a limit that looks enforced.
    """
    _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})

    verify_otp({'session_id': body['session_id'], 'code': '000000', 'phone_number': SUB_PHONE})
    assert PaymentVerificationSession.objects.get().attempts == 1

    verify_otp({'session_id': body['session_id'], 'code': '111111', 'phone_number': SUB_PHONE})
    assert PaymentVerificationSession.objects.get().attempts == 2


def test_an_unknown_session_is_refused(verify_otp):
    status_code, result = verify_otp(
        {
            'session_id': '11111111-2222-3333-4444-555555555555',
            'code': '123456',
            'phone_number': SUB_PHONE,
        }
    )

    assert status_code == 400
    assert result['code'] == 'SESSION_NOT_FOUND'


def test_a_malformed_session_id_does_not_raise(verify_otp):
    status_code, result = verify_otp(
        {'session_id': 'not-a-uuid', 'code': '123456', 'phone_number': SUB_PHONE}
    )

    assert status_code == 400
    assert result['code'] == 'SESSION_NOT_FOUND'


# ---------------------------------------------------------------------------
# Resending and rate limits
# ---------------------------------------------------------------------------


def test_a_resend_waits_for_the_cooldown(request_otp, tier):
    _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})

    status_code, result = request_otp(
        {
            'purpose': SUB,
            'tier_id': tier.id,
            'phone_number': SUB_PHONE,
            'session_id': body['session_id'],
        }
    )

    assert status_code == 429
    assert result['code'] == 'RESEND_COOLDOWN'
    assert result['retry_after'] > 0
    assert SmsMessage.objects.count() == 1, 'a second SMS went out during the cooldown'


def test_a_resend_after_the_cooldown_sends_a_new_code(request_otp, tier):
    from django.contrib.auth.hashers import check_password

    _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})
    first = sent_code()

    PaymentVerificationSession.objects.update(
        last_sent_at=timezone.now() - timedelta(seconds=payment_otp.RESEND_COOLDOWN_SECONDS + 1)
    )
    status_code, _ = request_otp(
        {
            'purpose': SUB,
            'tier_id': tier.id,
            'phone_number': SUB_PHONE,
            'session_id': body['session_id'],
        }
    )

    assert status_code == 200
    assert SmsMessage.objects.count() == 2
    assert not check_password(first, PaymentVerificationSession.objects.get().otp_hash)


def test_the_hourly_ceiling_stops_sending(request_otp, tier):
    for _ in range(payment_otp.MAX_SENDS_PER_PHONE_PER_HOUR):
        payment_otp._count_send(SUB_PHONE)

    status_code, result = request_otp(
        {'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE}
    )

    assert status_code == 429
    assert result['code'] == 'HOURLY_LIMIT'
    assert not SmsMessage.objects.exists(), 'an SMS went out past the hourly ceiling'


# ---------------------------------------------------------------------------
# SMS failure
# ---------------------------------------------------------------------------


def test_an_sms_that_cannot_be_queued_is_an_error(request_otp, tier):
    from unittest.mock import patch

    from api.services.sms.dispatch import SmsNotQueued

    with patch('api.services.sms.dispatch.queue_sms', side_effect=SmsNotQueued('gateway down')):
        status_code, result = request_otp(
            {'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE}
        )

    assert status_code == 502
    assert result['code'] == 'SMS_FAILED'
    assert not PaymentVerificationSession.objects.exists()


def test_an_sms_failure_stops_the_payment(request_otp, push_subscription, tier):
    from unittest.mock import patch

    from api.services.sms.dispatch import SmsNotQueued

    with patch('api.services.sms.dispatch.queue_sms', side_effect=SmsNotQueued('gateway down')):
        _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})

    with telebirr('subscription') as service:
        status_code, _ = push_subscription(
            {
                'tier_id': tier.id,
                'phone_number': SUB_PHONE,
                'verification_session_id': body.get('session_id'),
            }
        )

    assert status_code == 403
    service.initiate_ussd_push_payment.assert_not_called()


# ---------------------------------------------------------------------------
# The push itself
# ---------------------------------------------------------------------------


def test_a_push_without_any_verification_is_refused(push_subscription, tier):
    with telebirr('subscription') as service:
        status_code, body = push_subscription({'tier_id': tier.id, 'phone_number': SUB_PHONE})

    assert status_code == 403
    assert body['code'] == 'VERIFICATION_REQUIRED'
    service.initiate_ussd_push_payment.assert_not_called()


def test_a_push_on_an_unverified_session_is_refused(request_otp, push_subscription, tier):
    _, body = request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})

    with telebirr('subscription') as service:
        status_code, result = push_subscription(
            {
                'tier_id': tier.id,
                'phone_number': SUB_PHONE,
                'verification_session_id': body['session_id'],
            }
        )

    assert status_code == 403
    assert result['code'] == 'VERIFICATION_REQUIRED'
    service.initiate_ussd_push_payment.assert_not_called()


def test_a_verified_session_starts_the_push(request_otp, verify_otp, push_subscription, tier):
    session_id = verified_session(request_otp, verify_otp, tier)

    with telebirr('subscription') as service:
        service.initiate_ussd_push_payment.return_value = PUSH_ACCEPTED
        status_code, body = push_subscription(
            {
                'tier_id': tier.id,
                'phone_number': SUB_PHONE,
                'verification_session_id': session_id,
            }
        )

    assert status_code == 200
    assert body['success'] is True
    service.initiate_ussd_push_payment.assert_called_once()
    assert service.initiate_ussd_push_payment.call_args.kwargs['phone_number'] == SUB_PHONE


def test_a_verified_session_cannot_start_a_second_push(
    request_otp, verify_otp, push_subscription, tier
):
    from api.models.subscription import SubscriptionPayment, SubscriptionPlan

    session_id = verified_session(request_otp, verify_otp, tier)

    with telebirr('subscription') as service:
        service.initiate_ussd_push_payment.return_value = PUSH_ACCEPTED
        push_subscription(
            {
                'tier_id': tier.id,
                'phone_number': SUB_PHONE,
                'verification_session_id': session_id,
            }
        )

    # Clear what the first push left behind, so the duplicate guard is not
    # what refuses the retry -- the spent verification must refuse it alone.
    SubscriptionPayment.objects.all().delete()
    SubscriptionPlan.objects.filter(onevas_phone_number=SUB_PHONE).delete()

    with telebirr('subscription') as second:
        status_code, body = push_subscription(
            {
                'tier_id': tier.id,
                'phone_number': SUB_PHONE,
                'verification_session_id': session_id,
            }
        )

    assert status_code == 403
    assert body['code'] == 'VERIFICATION_ALREADY_USED'
    second.initiate_ussd_push_payment.assert_not_called()


def test_a_verified_session_expires(request_otp, verify_otp, push_subscription, tier):
    session_id = verified_session(request_otp, verify_otp, tier)
    PaymentVerificationSession.objects.update(
        session_expires_at=timezone.now() - timedelta(seconds=1)
    )

    with telebirr('subscription') as service:
        status_code, body = push_subscription(
            {
                'tier_id': tier.id,
                'phone_number': SUB_PHONE,
                'verification_session_id': session_id,
            }
        )

    assert status_code == 403
    assert body['code'] == 'VERIFICATION_EXPIRED'
    service.initiate_ussd_push_payment.assert_not_called()


# ---------------------------------------------------------------------------
# Bypass attempts
# ---------------------------------------------------------------------------


def test_claiming_otp_verified_authorises_nothing(push_subscription, tier):
    """The frontend cannot assert its own verification."""
    with telebirr('subscription') as service:
        status_code, body = push_subscription(
            {
                'tier_id': tier.id,
                'phone_number': SUB_PHONE,
                'otp_verified': True,
                'verified': True,
            }
        )

    assert status_code == 403
    assert body['code'] == 'VERIFICATION_REQUIRED'
    service.initiate_ussd_push_payment.assert_not_called()


def test_a_session_for_one_number_cannot_pay_for_another(
    request_otp, verify_otp, push_subscription, tier
):
    session_id = verified_session(request_otp, verify_otp, tier)

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


def test_a_session_for_one_tier_cannot_buy_another(request_otp, verify_otp, push_subscription):
    from api.models import SubscriptionTier

    tiers = list(SubscriptionTier.objects.filter(is_active=True)[:2])
    if len(tiers) < 2:
        pytest.skip('needs two active tiers')
    chosen, other = tiers

    session_id = verified_session(request_otp, verify_otp, chosen)

    with telebirr('subscription') as service:
        status_code, result = push_subscription(
            {
                'tier_id': other.id,
                'phone_number': SUB_PHONE,
                'verification_session_id': session_id,
            }
        )

    assert status_code == 403
    assert result['code'] == 'VERIFICATION_MISMATCH'
    service.initiate_ussd_push_payment.assert_not_called()


# ---------------------------------------------------------------------------
# Everything else stays as it was
# ---------------------------------------------------------------------------


def test_the_otp_endpoint_targets_the_number_the_push_will_charge(subscriber):
    """If these disagree the code goes to one handset and the push to another."""
    from api.views.payment_verification import phone_for_payment

    assert phone_for_payment(user=None, provided=SUB_PHONE) == SUB_PHONE
    assert phone_for_payment(user=subscriber, provided=SUB_PHONE) == SUB_PHONE
    assert phone_for_payment(user=subscriber, provided=None) == PHONE
    assert phone_for_payment(user=None, provided=None) is None


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


def test_payment_codes_use_their_own_sms_purpose(request_otp, tier):
    """So a payment code is never mistaken for a login code in the logs."""
    request_otp({'purpose': SUB, 'tier_id': tier.id, 'phone_number': SUB_PHONE})

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
    assert len(codes) > 190
