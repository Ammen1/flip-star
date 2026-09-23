"""
The SMS check that stands between choosing USSD Push and being charged.

Why this exists
---------------
A USSD Push arrives on the subscriber's handset as a PIN prompt. Anyone who
could reach the initiate endpoint with somebody else's number could make that
prompt appear -- repeatedly, and at a moment of their choosing. A subscriber
who is used to seeing the prompt after tapping Pay may approve one that nobody
asked for.

So before a push is sent, the person holding the SIM has to prove it: a code
goes out by SMS, comes back through the API, and only then is the push
initiated.

What a session is bound to
--------------------------
A verified session authorises ONE payment: the one whose details were known
when the code was sent. ``request_fingerprint`` is a digest of the caller, the
number, and the tier being subscribed to, recomputed at push time from the
actual request and compared. Changing the user, the number or the tier after
verifying produces a different digest and the push is refused, so a
verification can never be carried across to a different payment.

What is stored
--------------
Never the code. ``otp_hash`` holds a password hash of it, so the row is not
enough to authorise anything -- the same reason PINs are not stored in the
clear. Six digits is a small space, which is why the attempt ceiling and the
five-minute expiry are part of the design rather than decoration: they are
what makes the hash sufficient.

Relationship to OTPService
--------------------------
``api/services/otp.py`` handles login and registration codes, keyed by phone
number in the cache. It is deliberately not reused here. That service proves
"this number can receive SMS" and its marker is claimable by any flow that
asks; this one proves "the holder of this number approved this exact payment",
which has to be a durable row bound to the payment and consumed exactly once.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class PaymentVerificationSession(models.Model):
    """One SMS verification standing in front of one USSD Push."""

    #: The only flow that needs this. Buying coins does not: the buyer is
    #: already signed in, the number charged is the one on their own account,
    #: and making them re-prove a handset they have already authenticated with
    #: buys nothing. Subscribing does, because it is reachable with no account
    #: at all -- a phone number typed into a form is the only identity there
    #: is, and without a check anyone could raise a PIN prompt on any handset.
    PURPOSE_SUBSCRIPTION = 'subscription'
    PURPOSE_CHOICES = [
        (PURPOSE_SUBSCRIPTION, 'Subscription'),
    ]

    #: Waiting for the code.
    STATUS_PENDING = 'pending'
    #: Code accepted; the push may now be initiated, once.
    STATUS_VERIFIED = 'verified'
    #: The push has been initiated against it. Terminal.
    STATUS_CONSUMED = 'consumed'
    #: Too many wrong codes. Terminal -- a new session is required.
    STATUS_BLOCKED = 'blocked'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_VERIFIED, 'Verified'),
        (STATUS_CONSUMED, 'Consumed'),
        (STATUS_BLOCKED, 'Blocked'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Null for the subscription flow, which is reachable before anybody has an
    # account: the number is the only identity there is at that point. When it
    # IS set, the push endpoint requires the same user, so a session opened by
    # one account cannot be handed to another.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='payment_verification_sessions',
    )
    phone_number = models.CharField(max_length=20, db_index=True)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)

    #: sha256 of everything this verification is allowed to authorise.
    #: See api/services/payment_otp.fingerprint.
    request_fingerprint = models.CharField(max_length=64)

    #: A password hash of the code. Never the code.
    otp_hash = models.CharField(max_length=255)
    otp_expires_at = models.DateTimeField()

    #: Wrong codes tried against this session, up to MAX_ATTEMPTS.
    attempts = models.PositiveSmallIntegerField(default=0)
    #: Codes sent for this session, including the first, up to MAX_SENDS.
    send_count = models.PositiveSmallIntegerField(default=0)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    verified_at = models.DateTimeField(null=True, blank=True)
    #: When the verified state stops authorising a push. Set on verification;
    #: shorter than a login session because it is a standing permission to
    #: charge somebody.
    session_expires_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['phone_number', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]
        verbose_name = 'payment verification session'

    def __str__(self):
        # Masked: this ends up in the admin list, which is a place a phone
        # number does not need to be readable in full.
        digits = self.phone_number or ''
        masked = f'{digits[:5]}****{digits[-3:]}' if len(digits) > 6 else digits
        return f'{self.purpose} for {masked} ({self.status})'

    # -- questions the views ask -------------------------------------------

    def otp_is_expired(self, now=None) -> bool:
        return (now or timezone.now()) >= self.otp_expires_at

    def session_is_expired(self, now=None) -> bool:
        """True when a verified session has aged out of authorising a push."""
        if self.session_expires_at is None:
            return False
        return (now or timezone.now()) >= self.session_expires_at

    @property
    def attempts_remaining(self) -> int:
        from api.services.payment_otp import MAX_ATTEMPTS

        return max(0, MAX_ATTEMPTS - self.attempts)
