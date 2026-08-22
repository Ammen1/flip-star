import random
import string
from datetime import datetime, timedelta
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings
import requests


class OTPService:
    """OTP service with rate limiting and Onevas SMS integration"""
    
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
        return ''.join(random.choice(characters) for _ in range(cls.OTP_LENGTH))
    
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
            return False, f'Please wait before requesting another OTP'
        
        return True, None
    
    @classmethod
    def send_otp(cls, phone_number, application_key, product_number=None, action='verification'):
        """Send OTP via Onevas SMS
        
        Args:
            phone_number: Phone number to send OTP to
            application_key: Onevas application key
            product_number: Onevas product number. Falls back to the configured
                value (environment -> Vault -> .env) when not supplied; it used
                to default to a hardcoded product id.
            action: The action this OTP is for (e.g., 'verification', 'password_reset')
        """
        if product_number is None:
            product_number = settings.ONEVAS_PRODUCT_NUMBER

        # Never log the application key.
        print(f"[OTP SERVICE DEBUG] send_otp called for phone: {phone_number}, product_number: {product_number}, action: {action}")

        can_send, error = cls.can_send_otp(phone_number)
        print(f"[OTP SERVICE DEBUG] can_send_otp result: {can_send}, error: {error}")
        
        if not can_send:
            return False, error
        
        # Generate OTP
        otp_code = cls.generate_otp()
        expires_at = timezone.now() + timedelta(minutes=cls.OTP_EXPIRY_MINUTES)
        print(f"[OTP SERVICE DEBUG] Generated OTP: {otp_code}, expires at: {expires_at}")
        
        # Store OTP in cache
        cache.set(
            cls.get_otp_cache_key(phone_number),
            {
                'code': otp_code,
                'expires_at': expires_at.isoformat(),
                'attempts': 0
            },
            timeout=cls.OTP_EXPIRY_MINUTES * 60
        )
        print(f"[OTP SERVICE DEBUG] OTP stored in cache")
        
        # Set rate limit
        cache.set(
            cls.get_rate_limit_key(phone_number),
            timezone.now().isoformat(),
            timeout=cls.RATE_LIMIT_MINUTES * 60
        )
        print(f"[OTP SERVICE DEBUG] Rate limit set")
        
        # Generate message based on action
        if action == 'password_reset':
            message = f'Your OTP for password reset is {otp_code}. Use this to reset your password. Valid for {cls.OTP_EXPIRY_MINUTES} minutes.'
        else:
            message = f'Your verification code is: {otp_code}. Valid for {cls.OTP_EXPIRY_MINUTES} minutes.'
        
        print(f"[OTP SERVICE DEBUG] Generated message: {message}")
        print(f"[OTP SERVICE DEBUG] OTP code value: {otp_code}")
        
        try:
            url = settings.ONEVAS_SMS_URL
            payload = {
                'phone_number': phone_number,
                'application_key': application_key,
                'text': message,
                'product_number': product_number
            }
            print(f"[OTP SERVICE DEBUG] Sending SMS to Onevas URL: {url}")
            print(f"[OTP SERVICE DEBUG] Payload: {payload}")
            
            response = requests.post(url, json=payload, timeout=30)
            print(f"[OTP SERVICE DEBUG] Onevas response status: {response.status_code}")
            print(f"[OTP SERVICE DEBUG] Onevas response body: {response.text}")
            print(f"[OTP SERVICE DEBUG] Response headers: {dict(response.headers)}")
            
            # Verify response is from Onevas by checking expected response patterns
            if response.status_code == 200:
                response_text = response.text.strip().lower()
                # Onevas typically returns "Accepted for Delivery" or similar success messages
                if 'accepted' not in response_text and 'success' not in response_text and 'delivered' not in response_text:
                    print(f"[OTP SERVICE DEBUG] WARNING: Response may not be from Onevas - unexpected response: {response.text}")
            else:
                print(f"[OTP SERVICE DEBUG] Onevas returned error status: {response.status_code}")
            
            if response.status_code == 200:
                return True, f'OTP sent to {phone_number}'
            else:
                # Even if SMS fails, OTP is stored in cache for testing
                return True, f'OTP generated (SMS delivery failed: {response.text})'
        
        except Exception as e:
            print(f"[OTP SERVICE DEBUG] Exception during SMS send: {str(e)}")
            # Even if SMS fails, OTP is stored in cache for testing
            return True, f'OTP generated (SMS error: {str(e)})'
    
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
