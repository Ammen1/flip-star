import random
import string
from datetime import datetime, timedelta

from django.core.cache import cache
from django.utils import timezone


class OTPService:
    """OTP generation, rate limiting and verification.

    Codes are sent by SMS over TIMWE SMPP -- the only gateway there is; OneVAS
    has been removed.
    """

    OTP_LENGTH = 6
    OTP_EXPIRY_MINUTES = 5
    MAX_ATTEMPTS = 3
    RATE_LIMIT_MINUTES = 1  # 1 OTP per minute per phone number (reduced for testing)

    #: How long after verifying an OTP the number can still be used to register.
    #: Bounds the window in which a verified number is claimable.
    VERIFIED_TTL_MINUTES = 15

    @classmethod
    def generate_otp(cls):
        """Generate a 6-digit alphanumeric OTP"""
        characters = string.digits  # Only digits for simplicity
        # KNOWN ISSUE, deliberately not fixed here: `random` is a Mersenne
        # Twister, not a CSPRNG, so a few observed OTPs are enough to predict
        # later ones. `secrets.choice` is the drop-in fix.
        #
        # Left alone because the SMPP migration this comment arrived with was
        # explicitly scoped not to change OTP generation, and altering how
        # codes are produced is not a transport change. Raise it separately --
        # it affects login OTPs and subscription setup OTPs alike.
        return ''.join(
            random.choice(characters)  # noqa: S311 - see above; tracked, not accepted
            for _ in range(cls.OTP_LENGTH)
        )

    @classmethod
    def get_rate_limit_key(cls, phone_number):
        """Get cache key for rate limiting"""
        return f'otp_rate_limit:{phone_number}'

    @classmethod
    def get_otp_cache_key(cls, phone_number):
        """Get cache key for OTP storage"""
        return f'otp:{phone_number}'

    @classmethod
    def get_attempts_key(cls, phone_number):
        """Get cache key for attempt tracking"""
        return f'otp_attempts:{phone_number}'

    @classmethod
    def can_send_otp(cls, phone_number):
        """Check if OTP can be sent (rate limiting)"""
        rate_limit_key = cls.get_rate_limit_key(phone_number)

        # Check if user has exceeded rate limit
        last_sent = cache.get(rate_limit_key)
        if last_sent:
            return False, 'Please wait before requesting another OTP'

        return True, None

    @classmethod
    def send_otp(cls, phone_number, *, action='verification'):
        """Generate an OTP for ``phone_number`` and queue it by SMS over TIMWE.

        Args:
            phone_number: Phone number to send the OTP to.
            action: What the OTP is for, e.g. 'verification', 'login',
                'password_reset'. Chooses the wording and the SmsMessage
                purpose.

        This used to take a OneVAS application key and product number. They
        are gone: OneVAS has been removed and the TIMWE gateway needs neither.
        ``action`` is keyword-only so a caller still passing them positionally
        fails loudly instead of having the key read as the action.
        """
        print(f'[OTP SERVICE DEBUG] send_otp called for phone: {phone_number}, action: {action}')

        can_send, error = cls.can_send_otp(phone_number)
        print(f'[OTP SERVICE DEBUG] can_send_otp result: {can_send}, error: {error}')

        if not can_send:
            return False, error

        # Generate OTP
        otp_code = cls.generate_otp()
        expires_at = timezone.now() + timedelta(minutes=cls.OTP_EXPIRY_MINUTES)
        print(f'[OTP SERVICE DEBUG] Generated OTP: {otp_code}, expires at: {expires_at}')

        # Store OTP in cache
        cache.set(
            cls.get_otp_cache_key(phone_number),
            {'code': otp_code, 'expires_at': expires_at.isoformat(), 'attempts': 0},
            timeout=cls.OTP_EXPIRY_MINUTES * 60,
        )
        print('[OTP SERVICE DEBUG] OTP stored in cache')

        # Set rate limit
        cache.set(
            cls.get_rate_limit_key(phone_number),
            timezone.now().isoformat(),
            timeout=cls.RATE_LIMIT_MINUTES * 60,
        )
        print('[OTP SERVICE DEBUG] Rate limit set')

        # Generate message based on action
        if action == 'password_reset':
            message = f'Your OTP for password reset is {otp_code}. Use this to reset your password. Valid for {cls.OTP_EXPIRY_MINUTES} minutes.'
        else:
            message = f'Your verification code is: {otp_code}. Valid for {cls.OTP_EXPIRY_MINUTES} minutes.'

        print(f'[OTP SERVICE DEBUG] Generated message: {message}')
        print(f'[OTP SERVICE DEBUG] OTP code value: {otp_code}')

        # Queued, not sent inline. The OTP itself is already in the cache
        # above, so verification works the moment the subscriber receives the
        # message; blocking this call on an SMPP bind would make every login
        # wait on a telecom link.
        #
        # The OneVAS HTTP POST that used to be here is gone -- see
        # api/services/sms/ for the gateway abstraction.
        from api.services.sms.dispatch import SmsNotQueued, queue_sms

        try:
            queue_sms(
                phone_number=phone_number,
                text=message,
                purpose=f'otp_{action}' if action else 'otp',
            )
        except SmsNotQueued as exc:
            # The OTP is still valid and still cached -- the original code
            # returned success on a delivery failure for the same reason, and
            # that behaviour is preserved deliberately.
            return True, f'OTP generated (SMS not queued: {exc})'

        return True, f'OTP sent to {phone_number}'

    @classmethod
    def verify_otp(cls, phone_number, otp_code):
        """Verify OTP"""
        cache_key = cls.get_otp_cache_key(phone_number)
        otp_data = cache.get(cache_key)

        if not otp_data:
            return False, 'OTP expired or not found'

        # Check expiry
        expires_at = datetime.fromisoformat(otp_data['expires_at'])
        if timezone.now() > expires_at:
            cache.delete(cache_key)
            return False, 'OTP expired'

        # Check attempts
        attempts = otp_data.get('attempts', 0)
        if attempts >= cls.MAX_ATTEMPTS:
            cache.delete(cache_key)
            return False, f'Maximum attempts ({cls.MAX_ATTEMPTS}) exceeded'

        # Verify code
        if otp_data['code'] != otp_code:
            # Increment attempts
            otp_data['attempts'] = attempts + 1
            cache.set(cache_key, otp_data, timeout=cls.OTP_EXPIRY_MINUTES * 60)
            return False, f'Invalid OTP. {cls.MAX_ATTEMPTS - attempts - 1} attempts remaining'

        # OTP verified - delete from cache
        cache.delete(cache_key)

        # Record that this number completed verification. The code itself is now
        # gone, so registration needs a separate short-lived proof.
        cls.mark_verified(phone_number)

        return True, 'OTP verified successfully'

    @classmethod
    def reset_otp(cls, phone_number):
        """Reset OTP for a phone number"""
        cache_key = cls.get_otp_cache_key(phone_number)
        cache.delete(cache_key)
        return True, 'OTP reset'

    @classmethod
    def get_verified_cache_key(cls, phone_number):
        """Cache key holding proof that a number passed OTP verification."""
        return f'phone_verified:{phone_number}'

    @classmethod
    def mark_verified(cls, phone_number):
        """Record a completed verification, valid for VERIFIED_TTL_MINUTES."""
        cache.set(
            cls.get_verified_cache_key(phone_number),
            timezone.now().isoformat(),
            timeout=cls.VERIFIED_TTL_MINUTES * 60,
        )

    @classmethod
    def is_verified(cls, phone_number):
        """True when the number verified recently and has not been consumed."""
        return cache.get(cls.get_verified_cache_key(phone_number)) is not None

    @classmethod
    def consume_verification(cls, phone_number):
        """Atomically check and clear the marker so it cannot be reused.

        Returns True when a valid marker was present.
        """
        key = cls.get_verified_cache_key(phone_number)
        if cache.get(key) is None:
            return False
        cache.delete(key)
        return True
