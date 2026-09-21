"""
Telling a telebirr subscriber their plan is active.

Two flows, one rule: when a telebirr payment is confirmed and the plan
activates, the subscriber is told. The notice queues like every other
application message and goes over the configured MA/SMPP gateway -- the same
transport the short-code and TIMWE welcome SMS use. Telebirr notices used to
ride a second, SkyConnect HTTP gateway; that transport has been removed, and
these pin the behaviour that must not change with it gone.

What these pin, in order of how badly each would fail in production:

* **only on success.** A pending, failed or cancelled payment must send
  nothing. The message says the subscription is active; sending it before
  that is true is worse than sending nothing.
* **once.** Telebirr redelivers a callback until it is acknowledged. The
  SuperApp path had no idempotency key at all, so every redelivery queued
  another SMS to the same person.
* **never at the cost of the subscription.** A provider outage must not undo
  an activation the customer has paid for.
* **on the MA/SMPP default.** A telebirr notice pins no transport, so it rides
  whatever ``SMS_PROVIDER`` selects -- exactly like a short-code welcome.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from api.models import SubscriptionTier
from api.models.sms import SmsMessage
from api.models.subscription import SubscriptionPlan
from api.services.telebirr_subscription_sms import (
    PURPOSE,
    SUPERAPP,
    USSD,
    build_activation_message,
    notify_activated,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def subscriber():
    user = User.objects.create_user(username='telebirr_sub', password='x')
    profile = user.profile
    profile.phone_number = '251911528271'
    profile.save(update_fields=['phone_number'])
    return user


@pytest.fixture
def tier():
    return SubscriptionTier.objects.filter(duration_type='monthly').first()


@pytest.fixture
def plan(subscriber, tier):
    return SubscriptionPlan.objects.create(
        user=subscriber,
        tier=tier,
        status='active',
        payment_method='telebirr',
        telebirr_phone_number='251911528271',
        start_date=timezone.now(),
        end_date=timezone.now() + timedelta(days=30),
    )


# ── the two telebirr flows send ─────────────────────────────────────────────


def test_a_confirmed_ussd_subscription_is_announced(plan):
    message = notify_activated(plan, source=USSD)

    assert message is not None
    assert message.provider == '', 'must ride the MA/SMPP default, not a pinned transport'
    assert message.recipient == '251911528271'
    assert 'activated successfully' in message.body


def test_a_confirmed_superapp_subscription_is_announced(plan):
    message = notify_activated(plan, source=SUPERAPP)

    assert message is not None
    assert message.provider == ''
    assert message.purpose == PURPOSE


def test_a_telebirr_notice_is_not_pinned_to_a_transport(plan):
    from api.services.sms.dispatch import queue_sms

    queue_sms(
        phone_number='251911528271',
        text='otp 123456',
        purpose='otp_login',
        idempotency_key='otp-1',
    )
    notify_activated(plan, source=USSD)

    messages = SmsMessage.objects.all()
    assert messages.count() == 2
    assert all(m.provider == '' for m in messages), 'no message names a private gateway'
    assert messages.filter(purpose=PURPOSE).count() == 1


def test_the_message_names_the_plan_and_when_it_ends(plan):
    body = build_activation_message(plan)

    assert plan.tier.name in body
    assert plan.end_date.strftime('%Y-%m-%d') in body


def test_the_message_does_not_tell_telebirr_users_to_text_a_short_code(plan):
    """The short-code welcome SMS quotes an OTP and a STOP keyword. Reusing it
    would give a telebirr subscriber instructions that do not work."""
    body = build_activation_message(plan)

    assert 'STOP' not in body
    assert 'OTP' not in body


# ── duplicates ──────────────────────────────────────────────────────────────


def test_a_redelivered_callback_sends_one_message(plan):
    first = notify_activated(plan, source=USSD)
    second = notify_activated(plan, source=USSD)
    third = notify_activated(plan, source=USSD)

    assert first.id == second.id == third.id
    assert SmsMessage.objects.filter(purpose=PURPOSE).count() == 1


def test_the_key_is_the_payment_when_there_is_one(plan):
    """A payment is exactly one activation, so it is the better anchor."""

    class _Payment:
        pk = 'payment-1'

    keyed = notify_activated(plan, source=USSD, payment=_Payment())

    assert 'payment-1' in keyed.idempotency_key


# ── nothing is sent before or without success ───────────────────────────────


def test_nothing_is_sent_without_a_plan():
    assert notify_activated(None, source=USSD) is None
    assert not SmsMessage.objects.exists()


def test_nothing_is_sent_to_a_subscriber_with_no_number(tier):
    user = User.objects.create_user(username='no_number', password='x')
    plan = SubscriptionPlan.objects.create(
        user=user, tier=tier, status='active', payment_method='telebirr'
    )

    assert notify_activated(plan, source=USSD) is None
    assert not SmsMessage.objects.exists()


def test_an_activation_survives_a_dispatch_failure(plan):
    """The subscription is already paid for. A notification that cannot even
    be queued must not raise into the caller's transaction."""
    with patch('api.services.sms.dispatch.queue_sms', side_effect=RuntimeError('database on fire')):
        assert notify_activated(plan, source=USSD) is None

    plan.refresh_from_db()
    assert plan.status == 'active', 'the activation was rolled back'


# ── the MA/SMPP default carries everything ──────────────────────────────────


def test_the_default_provider_is_still_smpp():
    from django.conf import settings

    assert getattr(settings, 'SMS_PROVIDER', '') == 'timwe_smpp'


def test_a_message_with_no_provider_uses_the_configured_default():
    from api.services.sms import get_gateway

    assert get_gateway().name == 'timwe_smpp'


def test_a_timwe_subscription_sms_still_goes_over_smpp():
    """The short-code flow queues without naming a provider, so it keeps the
    configured default -- which is what leaves TIMWE exactly as it was."""
    from api.services.sms.dispatch import queue_sms

    message = queue_sms(
        phone_number='251911528271',
        text='Dear valued customer, you have successfully subscribed...',
        purpose='subscription_welcome',
        idempotency_key='timwe-welcome-1',
    )

    assert message.provider == '', 'a TIMWE message must not be pinned to a provider'


# ── the amount is not invented ──────────────────────────────────────────────


def test_a_plan_without_a_tier_still_produces_a_sensible_message(subscriber):
    plan = SubscriptionPlan.objects.create(
        user=subscriber,
        tier=None,
        status='active',
        payment_method='telebirr',
        telebirr_phone_number='251911528271',
        end_date=timezone.now() + timedelta(days=7),
    )

    body = build_activation_message(plan)
    assert 'Your Flipstar subscription has been activated successfully.' in body
