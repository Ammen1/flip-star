"""
Generating, checking and spending the SMS code that authorises a USSD Push.

The rules, in one place
-----------------------
* Six digits from ``secrets``, never ``random``. A USSD Push is a prompt to
  hand over money; a predictable code would let somebody else raise it.
* The code is hashed on the way in and compared with a constant-time check.
  Nothing here returns it, logs it, or puts it in a response.
* Five minutes to use it, matching ``OTPService.OTP_EXPIRY_MINUTES`` so
  subscribers meet one convention rather than two.
* Five wrong tries and the session is finished -- not the code re-rolled, the
  session. Six digits is a million possibilities and an attacker who may keep
  guessing eventually arrives.
* A verified session authorises exactly one push, for exactly the payment it
  was opened for, within ten minutes, once.

Why not OTPService
------------------
``api/services/otp.py`` answers "can this number receive SMS", stores the code
in the cache under the number alone, and leaves a marker any flow may claim.
None of that binds a code to a payment, and its send path deliberately reports
success when the SMS could not be queued -- correct for a login the user can
retry, wrong here, where a code nobody received must not leave a session
looking half-open. This module is separate for those reasons, and uses the
same SMS queue underneath so there is still one way out to the handset.
"""

from __future__ import annotations

import hashlib
import logging
import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from api.models.payment_verification import PaymentVerificationSession

logger = logging.getLogger(__name__)

OTP_LENGTH = 6
#: Matches OTPService.OTP_EXPIRY_MINUTES -- one convention for subscribers.
OTP_TTL_SECONDS = 5 * 60
#: How long a verified session may authorise a push before it has to be redone.
VERIFIED_TTL_SECONDS = 10 * 60

#: Wrong codes allowed per session before it is finished for good.
MAX_ATTEMPTS = 5
#: Codes sendable within one session, the first included.
MAX_SENDS_PER_SESSION = 3
#: Between one code and the next, for the same session.
RESEND_COOLDOWN_SECONDS = 60
#: Codes sendable to one number across all sessions, per hour.
MAX_SENDS_PER_PHONE_PER_HOUR = 5


class OtpRequestRefused(Exception):
    """Refusing to send a code. ``code`` is for the client to branch on."""

    def __init__(self, message, code, *, retry_after=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retry_after = retry_after


class OtpVerificationFailed(Exception):
    """The code was not accepted. ``attempts_remaining`` may be None."""

    def __init__(self, message, code, *, attempts_remaining=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.attempts_remaining = attempts_remaining


def mask(phone_number: str) -> str:
    """A number safe to log: enough to identify a report, not to dial."""
    digits = phone_number or ''
    return f'{digits[:5]}****{digits[-3:]}' if len(digits) > 6 else digits


def generate_code() -> str:
    """Six digits from a CSPRNG, leading zeros kept."""
    return ''.join(secrets.choice('0123456789') for _ in range(OTP_LENGTH))


def fingerprint(*, purpose, user_id, phone_number, tier_id=None):
    """Everything a verification is allowed to authorise, as one digest.

    Recomputed at push time from the request actually being made. Any
    difference -- a different account, number, package, tier or amount --
    yields a different digest, so a session verified for one payment cannot
    authorise another.

    ``None`` and ``''`` deliberately collapse to the same empty field, so a
    missing tier is a missing tier however the client spelled it.
    """
    parts = [
        str(purpose or ''),
        str(user_id or ''),
        str(phone_number or ''),
        str(tier_id or ''),
    ]
    return hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()


def _phone_hour_key(phone_number: str) -> str:
    return f'payment_otp_sends:{phone_number}'


def _count_send(phone_number: str) -> None:
    key = _phone_hour_key(phone_number)
    # add() only sets when absent, so the hour window starts at the first send
    # and does not slide forward with each one.
    cache.add(key, 0, timeout=3600)
    try:
        cache.incr(key)
    except ValueError:
        # The key expired between add and incr. Start a fresh window.
        cache.set(key, 1, timeout=3600)


def sends_this_hour(phone_number: str) -> int:
    return cache.get(_phone_hour_key(phone_number), 0)


def request_otp(
    *,
    purpose,
    phone_number,
    user=None,
    tier_id=None,
    session_id=None,
):
    """Open (or resend on) a verification session. Returns the session.

    Raises ``OtpRequestRefused`` when a limit says no, or when the SMS cannot
    be queued -- in which case no usable session is left behind, because a
    code nobody received must not look like a step the subscriber can finish.
    """
    now = timezone.now()
    digest = fingerprint(
        purpose=purpose,
        user_id=getattr(user, 'id', None),
        phone_number=phone_number,
        tier_id=tier_id,
    )

    session = None
    if session_id:
        session = (
            PaymentVerificationSession.objects.filter(
                id=session_id,
                request_fingerprint=digest,
                status=PaymentVerificationSession.STATUS_PENDING,
            )
            .filter(user=user)
            .first()
        )
        if session is None:
            # Not an error worth distinguishing for the caller: an unknown,
            # finished or mismatched session just starts a new one.
            session = None

    if session is not None:
        if session.last_sent_at and (now - session.last_sent_at).total_seconds() < (
            RESEND_COOLDOWN_SECONDS
        ):
            wait = RESEND_COOLDOWN_SECONDS - int((now - session.last_sent_at).total_seconds())
            raise OtpRequestRefused(
                f'Please wait {wait} seconds before asking for another code.',
                'RESEND_COOLDOWN',
                retry_after=wait,
            )
        if session.send_count >= MAX_SENDS_PER_SESSION:
            raise OtpRequestRefused(
                'Too many codes have been sent for this payment. Start again.',
                'TOO_MANY_SENDS',
            )

    if sends_this_hour(phone_number) >= MAX_SENDS_PER_PHONE_PER_HOUR:
        raise OtpRequestRefused(
            'Too many verification codes requested. Please try again later.',
            'HOURLY_LIMIT',
        )

    code = generate_code()
    hashed = make_password(code)

    if session is None:
        session = PaymentVerificationSession(
            user=user,
            phone_number=phone_number,
            purpose=purpose,
            request_fingerprint=digest,
        )
    session.otp_hash = hashed
    session.otp_expires_at = now + timezone.timedelta(seconds=OTP_TTL_SECONDS)
    session.attempts = 0
    session.send_count = (session.send_count or 0) + 1
    session.last_sent_at = now
    session.status = PaymentVerificationSession.STATUS_PENDING
    session.save()

    try:
        _send_code(phone_number=phone_number, code=code, session=session)
    except Exception:
        # Nothing reached the handset, so nothing here may be verifiable. The
        # row goes rather than being left pending: a session whose code does
        # not exist is a step the subscriber cannot complete.
        session.delete()
        logger.warning(
            'Payment OTP not sent to %s (purpose=%s); session discarded',
            mask(phone_number),
            purpose,
            extra={'operation': 'payment_otp_request', 'result': 'sms_failed'},
        )
        raise OtpRequestRefused(
            'We could not send the verification code. Please try again.',
            'SMS_FAILED',
        ) from None

    _count_send(phone_number)
    logger.info(
        'Payment OTP sent to %s session=%s purpose=%s send=%s',
        mask(phone_number),
        session.id,
        purpose,
        session.send_count,
        extra={'operation': 'payment_otp_request', 'result': 'sent'},
    )
    return session


def _send_code(*, phone_number, code, session):
    """Hand the message to the existing SMS queue. The only way out to a handset."""
    from api.services.sms.dispatch import queue_sms

    # Kept short deliberately, and measured by tests.
    #
    # The first wording was 99 characters -- one GSM-7 segment, well inside
    # the 160 the spec allows -- and TIMWE's SMPP gateway refused every one
    # with ESME_RINVMSGLEN (status 1) while accepting a 92-character message
    # on the same bind, same encoding, same source address. So their limit is
    # lower than the standard's, somewhere between the two, and they report
    # exceeding it as a length error.
    #
    # tests/integration/test_subscription_and_withdrawal_sms.py holds every
    # outbound message to one segment; this one is additionally held under the
    # shortest length TIMWE have been observed to accept.
    minutes = OTP_TTL_SECONDS // 60
    text = f'FlipStar payment code: {code}. Expires in {minutes} min. Do not share.'
    queue_sms(
        phone_number=phone_number,
        text=text,
        purpose='otp_payment_verification',
        # One message per send attempt, so a retried request cannot fan out
        # into several SMS for the same code.
        idempotency_key=f'payment-otp:{session.id}:{session.send_count}',
    )


def verify_otp(*, session_id, code, phone_number, user=None):
    """Check a code against its session. Returns the verified session.

    Raises ``OtpVerificationFailed`` for every rejection, with a ``code`` the
    client can branch on and, where it helps, how many tries are left.

    Nothing raises inside the transaction. A failed attempt has to increment
    ``attempts`` and that increment has to survive -- raising from inside the
    atomic block rolls it back, which would let somebody guess for ever at a
    counter that always read zero. So the outcome is decided under the lock
    and reported once it has been committed.
    """
    now = timezone.now()
    failure = None
    session = None

    with transaction.atomic():
        session = (
            PaymentVerificationSession.objects.select_for_update().filter(id=session_id).first()
            if _uuid_like(session_id)
            else None
        )

        if session is None:
            failure = (
                'This verification has expired. Please start again.',
                'SESSION_NOT_FOUND',
                None,
            )

        # The session belongs to whoever opened it. A code sent to one number
        # cannot be presented for another, and one account's session cannot be
        # verified by a different account.
        elif session.phone_number != phone_number or session.user_id != getattr(user, 'id', None):
            logger.warning(
                'Payment OTP rejected: session=%s does not belong to this caller',
                session.id,
                extra={'operation': 'payment_otp_verify', 'result': 'wrong_owner'},
            )
            failure = ('This verification does not match this payment.', 'SESSION_MISMATCH', None)

        elif session.status == PaymentVerificationSession.STATUS_BLOCKED:
            failure = ('Too many incorrect codes. Please start again.', 'TOO_MANY_ATTEMPTS', 0)

        elif session.status != PaymentVerificationSession.STATUS_PENDING:
            # Already verified or already spent. Neither may be re-verified,
            # which is what stops a consumed session being revived.
            failure = ('This verification has already been used.', 'ALREADY_USED', None)

        elif session.otp_is_expired(now):
            failure = ('This code has expired. Please ask for a new one.', 'OTP_EXPIRED', None)

        elif not check_password(str(code or ''), session.otp_hash):
            session.attempts += 1
            if session.attempts >= MAX_ATTEMPTS:
                session.status = PaymentVerificationSession.STATUS_BLOCKED
                session.save(update_fields=['attempts', 'status'])
                logger.warning(
                    'Payment OTP blocked after %s attempts session=%s phone=%s',
                    session.attempts,
                    session.id,
                    mask(session.phone_number),
                    extra={'operation': 'payment_otp_verify', 'result': 'blocked'},
                )
                failure = ('Too many incorrect codes. Please start again.', 'TOO_MANY_ATTEMPTS', 0)
            else:
                session.save(update_fields=['attempts'])
                logger.info(
                    'Payment OTP incorrect session=%s phone=%s remaining=%s',
                    session.id,
                    mask(session.phone_number),
                    session.attempts_remaining,
                    extra={'operation': 'payment_otp_verify', 'result': 'incorrect'},
                )
                failure = ('That code is not correct.', 'OTP_INVALID', session.attempts_remaining)

        else:
            session.status = PaymentVerificationSession.STATUS_VERIFIED
            session.verified_at = now
            session.session_expires_at = now + timezone.timedelta(seconds=VERIFIED_TTL_SECONDS)
            # The hash goes: it has done its job, and a verified row should not
            # still carry something worth attacking.
            session.otp_hash = ''
            session.save(update_fields=['status', 'verified_at', 'session_expires_at', 'otp_hash'])

    if failure is not None:
        message, failure_code, remaining = failure
        raise OtpVerificationFailed(message, failure_code, attempts_remaining=remaining)

    logger.info(
        'Payment OTP verified session=%s phone=%s purpose=%s',
        session.id,
        mask(session.phone_number),
        session.purpose,
        extra={'operation': 'payment_otp_verify', 'result': 'verified'},
    )
    return session


def _uuid_like(value) -> bool:
    """Guard the UUID column against a malformed id, which would raise."""
    import uuid as _uuid

    try:
        _uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def consume_verified_session(
    *,
    session_id,
    purpose,
    phone_number,
    user=None,
    tier_id=None,
):
    """Spend a verified session to authorise one push. Returns the session.

    Every check here is the point of the feature, so none of it is optional:
    the session must exist, be verified rather than pending or spent, still be
    within its window, and describe this exact payment. It is marked consumed
    in the same conditional update that claims it, so two simultaneous pushes
    cannot both win.

    Raises ``OtpVerificationFailed``; the caller turns that into a 403.
    """
    if not _uuid_like(session_id):
        raise OtpVerificationFailed(
            'Phone verification is required before payment.', 'VERIFICATION_REQUIRED'
        )

    now = timezone.now()
    digest = fingerprint(
        purpose=purpose,
        user_id=getattr(user, 'id', None),
        phone_number=phone_number,
        tier_id=tier_id,
    )

    # One conditional UPDATE does the claiming. Filtering on the fingerprint
    # and on status='verified' means a row that does not describe this
    # payment, or has already been spent, simply does not match -- there is no
    # window between deciding and marking in which a second request could slip
    # through.
    claimed = PaymentVerificationSession.objects.filter(
        id=session_id,
        status=PaymentVerificationSession.STATUS_VERIFIED,
        request_fingerprint=digest,
        phone_number=phone_number,
        user=user,
        session_expires_at__gt=now,
    ).update(status=PaymentVerificationSession.STATUS_CONSUMED, consumed_at=now)

    if not claimed:
        # Work out why, for the message only -- the refusal already happened.
        session = PaymentVerificationSession.objects.filter(id=session_id).first()
        reason, code = _explain_refusal(session, digest, now)
        logger.warning(
            'USSD Push refused: %s session=%s phone=%s purpose=%s',
            code,
            session_id,
            mask(phone_number),
            purpose,
            extra={'operation': 'ussd_push_verification', 'result': 'refused'},
        )
        raise OtpVerificationFailed(reason, code)

    session = PaymentVerificationSession.objects.get(id=session_id)
    logger.info(
        'USSD Push authorised by session=%s phone=%s purpose=%s',
        session.id,
        mask(phone_number),
        purpose,
        extra={'operation': 'ussd_push_verification', 'result': 'authorised'},
    )
    return session


def _explain_refusal(session, digest, now):
    if session is None:
        return 'Phone verification is required before payment.', 'VERIFICATION_REQUIRED'
    if session.status == PaymentVerificationSession.STATUS_CONSUMED:
        return 'This verification has already been used.', 'VERIFICATION_ALREADY_USED'
    if session.status == PaymentVerificationSession.STATUS_PENDING:
        return 'Please enter the code we sent by SMS.', 'VERIFICATION_REQUIRED'
    if session.status == PaymentVerificationSession.STATUS_BLOCKED:
        return 'Too many incorrect codes. Please start again.', 'TOO_MANY_ATTEMPTS'
    if session.session_expires_at is not None and session.session_expires_at <= now:
        return 'This verification has expired. Please verify again.', 'VERIFICATION_EXPIRED'
    if session.request_fingerprint != digest:
        return 'This verification does not match this payment.', 'VERIFICATION_MISMATCH'
    return 'Phone verification is required before payment.', 'VERIFICATION_REQUIRED'
