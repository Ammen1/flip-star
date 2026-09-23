"""
The SMS check in front of a USSD Push.

    POST /charging/ussd-push/request-otp/   send a code to the payer's number
    POST /charging/ussd-push/verify-otp/    check it, and open the payment

Neither endpoint moves money, and neither returns the code. What a successful
verification produces is a session id the push endpoints will accept once --
see ``api/services/payment_otp.consume_verified_session``, which is where the
guarantee actually lives. Nothing the client can say substitutes for it: there
is no ``otp_verified`` flag anywhere in this flow, because a flag is a claim
and a session row is a fact.

``AllowAny`` is deliberate. The subscription flow reaches USSD Push before the
payer has an account -- ``telebirr_ussd_subscription_initiate`` is AllowAny
for the same reason -- so requiring a token here would lock out the flow this
was written to protect. A coin purchase still requires a login, checked below.
"""

import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.models.payment_verification import PaymentVerificationSession
from api.services import payment_otp
from api.services.payment_otp import (
    MAX_ATTEMPTS,
    OTP_TTL_SECONDS,
    RESEND_COOLDOWN_SECONDS,
    OtpRequestRefused,
    OtpVerificationFailed,
)
from common.security import encrypted_endpoint
from common.throttling import (
    OtpSendAnonThrottle,
    OtpSendUserThrottle,
    OtpVerifyAnonThrottle,
    OtpVerifyUserThrottle,
)

logger = logging.getLogger(__name__)

PURPOSES = (
    PaymentVerificationSession.PURPOSE_COIN_PURCHASE,
    PaymentVerificationSession.PURPOSE_SUBSCRIPTION,
)


def phone_for_payment(*, user, provided, purpose):
    """The number a payment of this kind will actually be sent to.

    This MUST match how the push endpoints resolve it, or a code goes to one
    number while the push goes to another and every payment is refused on a
    fingerprint mismatch. The rules are theirs, restated:

    * coin purchase -- the account's own profile number, never the client's.
      ``telebirr_ussd_purchase`` ignores any number in the body.
    * subscription -- the number in the body when there is one (the payer may
      have no account yet), otherwise the profile's.

    ``tests/integration/test_ussd_push_otp.py`` pins the agreement.
    """
    from api.views.core import _normalize_ethiopian_phone

    authenticated = bool(user and user.is_authenticated)
    profile = getattr(user, 'profile', None) if authenticated else None
    profile_phone = getattr(profile, 'phone_number', None)

    if purpose == PaymentVerificationSession.PURPOSE_COIN_PURCHASE:
        raw = profile_phone
    else:
        raw = provided or profile_phone

    if not raw:
        return None
    return _normalize_ethiopian_phone(raw) or raw


def _payment_reference(data):
    """The three fields that say which payment this is."""
    return {
        'package_id': data.get('package_id'),
        'tier_id': data.get('tier_id'),
        'amount_etb': data.get('amount_etb'),
    }


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([OtpSendAnonThrottle, OtpSendUserThrottle])
@encrypted_endpoint
def request_ussd_push_otp(request):
    """Send a verification code to the number that will be charged."""
    data = request.data
    purpose = (data.get('purpose') or '').strip()

    if purpose not in PURPOSES:
        return Response(
            {'error': 'Unknown payment type.', 'code': 'INVALID_PURPOSE'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = request.user if request.user.is_authenticated else None

    # Buying coins is an account action; subscribing is not, yet.
    if purpose == PaymentVerificationSession.PURPOSE_COIN_PURCHASE and user is None:
        return Response(
            {'error': 'Please sign in to buy coins.', 'code': 'AUTHENTICATION_REQUIRED'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    reference = _payment_reference(data)
    if purpose == PaymentVerificationSession.PURPOSE_SUBSCRIPTION and not reference['tier_id']:
        return Response(
            {'error': 'tier_id is required', 'code': 'TIER_REQUIRED'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if purpose == PaymentVerificationSession.PURPOSE_COIN_PURCHASE and not (
        reference['package_id'] or reference['amount_etb']
    ):
        return Response(
            {'error': 'package_id or amount_etb is required', 'code': 'PACKAGE_REQUIRED'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    phone_number = phone_for_payment(user=user, provided=data.get('phone_number'), purpose=purpose)
    if not phone_number:
        return Response(
            {'error': 'A phone number is required.', 'code': 'PHONE_REQUIRED'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        session = payment_otp.request_otp(
            purpose=purpose,
            phone_number=phone_number,
            user=user,
            session_id=data.get('session_id'),
            **reference,
        )
    except OtpRequestRefused as refused:
        body = {'error': refused.message, 'code': refused.code}
        if refused.retry_after is not None:
            body['retry_after'] = refused.retry_after
        # 429 for a limit, 502 for a gateway that would not take the message.
        http_status = (
            status.HTTP_502_BAD_GATEWAY
            if refused.code == 'SMS_FAILED'
            else status.HTTP_429_TOO_MANY_REQUESTS
        )
        return Response(body, status=http_status)

    # No code in here, and none in the logs. The masked number is so the payer
    # can see which handset to look at.
    return Response(
        {
            'success': True,
            'session_id': str(session.id),
            'phone_number': payment_otp.mask(phone_number),
            'expires_in': OTP_TTL_SECONDS,
            'resend_after': RESEND_COOLDOWN_SECONDS,
            'attempts_allowed': MAX_ATTEMPTS,
        },
        status=status.HTTP_200_OK,
    )


@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([OtpVerifyAnonThrottle, OtpVerifyUserThrottle])
@encrypted_endpoint
def verify_ussd_push_otp(request):
    """Check the code. On success the session may authorise one push."""
    data = request.data
    session_id = data.get('session_id')
    code = data.get('code') or data.get('otp')

    if not session_id or not code:
        return Response(
            {'error': 'Enter the 6-digit code we sent by SMS.', 'code': 'OTP_REQUIRED'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = request.user if request.user.is_authenticated else None
    purpose = (data.get('purpose') or '').strip()
    phone_number = phone_for_payment(
        user=user,
        provided=data.get('phone_number'),
        purpose=purpose if purpose in PURPOSES else PaymentVerificationSession.PURPOSE_SUBSCRIPTION,
    )

    try:
        session = payment_otp.verify_otp(
            session_id=session_id,
            code=code,
            phone_number=phone_number,
            user=user,
        )
    except OtpVerificationFailed as failure:
        body = {'error': failure.message, 'code': failure.code}
        if failure.attempts_remaining is not None:
            body['attempts_remaining'] = failure.attempts_remaining
        return Response(body, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        {
            'success': True,
            'session_id': str(session.id),
            'verified': True,
            'expires_in': int((session.session_expires_at - session.verified_at).total_seconds()),
        },
        status=status.HTTP_200_OK,
    )
