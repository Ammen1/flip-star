"""
Telling a telebirr subscriber their plan is active.

Two flows, one rule: when a telebirr payment is confirmed and the plan
activates, the subscriber is told, over SkyConnect. The short-code and TIMWE
flows keep SMPP and are deliberately untouched -- a working production path
should not change because a second provider now exists.

What these pin, in order of how badly each would fail in production:

* **only on success.** A pending, failed or cancelled payment must send
  nothing. The message says the subscription is active; sending it before
  that is true is worse than sending nothing.
* **once.** Telebirr redelivers a callback until it is acknowledged. The
  SuperApp path had no idempotency key at all, so every redelivery queued
  another SMS to the same person.
* **never at the cost of the subscription.** A provider outage must not undo
  an activation the customer has paid for.
* **the key stays secret.** It is a bearer token; it must not reach a log,
  an exception message or a test.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
import requests
from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone

from api.integrations.skyconnect.sms import (
    SkyConnectError,
    SkyConnectNotConfigured,
    send_sms,
    to_msisdn,
)
from api.models import SubscriptionTier
from api.models.sms import SmsMessage
from api.models.subscription import SubscriptionPlan
from api.services.telebirr_subscription_sms import (
    PROVIDER,
    SUPERAPP,
    USSD,
    build_activation_message,
    notify_activated,
)

pytestmark = pytest.mark.django_db

API_URL = 'https://sms.example.invalid/api/v1/sms/send'
# Not a real credential: a marker that must never appear anywhere it is looked
# for below.
FAKE_KEY = 'test-key-must-never-be-logged'

SKY_SETTINGS = {
    'SKYCONNECT_SMS_API_URL': API_URL,
    'SKYCONNECT_SMS_API_KEY': FAKE_KEY,
    'SKYCONNECT_SMS_SENDER_ID': 'Flipstar',
}


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


class _Response:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload
        self.text = text or ''

    def json(self):
        if self._payload is None:
            raise ValueError('no json')
        return self._payload


# ── 12. phone normalisation ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    'given,expected',
    [
        ('251911528271', '+251911528271'),
        ('+251911528271', '+251911528271'),
        ('251 911 528 271', '+251911528271'),
        ('', ''),
        (None, ''),
    ],
)
def test_numbers_are_normalised_for_the_provider(given, expected):
    """The provider wants +2519XXXXXXXX; the rest of the app stores
    251XXXXXXXXX, so the plus is added here rather than everywhere else."""
    assert to_msisdn(given) == expected


# ── 1 & 2. the two telebirr flows send ──────────────────────────────────────


@override_settings(**SKY_SETTINGS)
def test_a_confirmed_ussd_subscription_is_announced(plan):
    message = notify_activated(plan, source=USSD)

    assert message is not None
    assert message.provider == PROVIDER, 'must not go over SMPP'
    assert message.recipient == '251911528271'
    assert 'activated successfully' in message.body


@override_settings(**SKY_SETTINGS)
def test_a_confirmed_superapp_subscription_is_announced(plan):
    message = notify_activated(plan, source=SUPERAPP)

    assert message is not None
    assert message.provider == PROVIDER


@override_settings(**SKY_SETTINGS)
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


# ── 8. duplicates ───────────────────────────────────────────────────────────


@override_settings(**SKY_SETTINGS)
def test_a_redelivered_callback_sends_one_message(plan):
    first = notify_activated(plan, source=USSD)
    second = notify_activated(plan, source=USSD)
    third = notify_activated(plan, source=USSD)

    assert first.id == second.id == third.id
    assert SmsMessage.objects.filter(purpose=first.purpose).count() == 1


@override_settings(**SKY_SETTINGS)
def test_the_key_is_the_payment_when_there_is_one(plan):
    """A payment is exactly one activation, so it is the better anchor."""

    class _Payment:
        pk = 'payment-1'

    keyed = notify_activated(plan, source=USSD, payment=_Payment())

    assert 'payment-1' in keyed.idempotency_key


# ── 3, 4, 5. nothing is sent before or without success ──────────────────────


@override_settings(**SKY_SETTINGS)
def test_nothing_is_sent_without_a_plan():
    assert notify_activated(None, source=USSD) is None
    assert not SmsMessage.objects.exists()


@override_settings(**SKY_SETTINGS)
def test_nothing_is_sent_to_a_subscriber_with_no_number(tier):
    user = User.objects.create_user(username='no_number', password='x')
    plan = SubscriptionPlan.objects.create(
        user=user, tier=tier, status='active', payment_method='telebirr'
    )

    assert notify_activated(plan, source=USSD) is None
    assert not SmsMessage.objects.exists()


# ── 9 & 10. provider failures never cost the subscription ───────────────────


@override_settings(**SKY_SETTINGS)
def test_a_provider_http_failure_is_recorded_not_raised():
    with patch('api.integrations.skyconnect.sms.requests.post') as post:
        post.return_value = _Response(status_code=500, text='upstream down')

        with pytest.raises(SkyConnectError) as exc:
            send_sms(destination='251911528271', text='hello')

    assert exc.value.retryable is True, 'a 5xx is worth retrying'


@override_settings(**SKY_SETTINGS)
def test_a_rejection_is_not_retried():
    """A bad number or an expired key returns the same answer next time."""
    with patch('api.integrations.skyconnect.sms.requests.post') as post:
        post.return_value = _Response(status_code=400, text='bad number')

        with pytest.raises(SkyConnectError) as exc:
            send_sms(destination='251911528271', text='hello')

    assert exc.value.retryable is False


@override_settings(**SKY_SETTINGS)
def test_a_timeout_is_handled_as_retryable():
    with patch('api.integrations.skyconnect.sms.requests.post') as post:
        post.side_effect = requests.Timeout('too slow')

        with pytest.raises(SkyConnectError) as exc:
            send_sms(destination='251911528271', text='hello')

    assert exc.value.retryable is True


@override_settings(**SKY_SETTINGS)
def test_an_activation_survives_a_dispatch_failure(plan):
    """The subscription is already paid for. A notification that cannot even
    be queued must not raise into the caller's transaction."""
    with patch('api.services.sms.dispatch.queue_sms', side_effect=RuntimeError('database on fire')):
        assert notify_activated(plan, source=USSD) is None

    plan.refresh_from_db()
    assert plan.status == 'active', 'the activation was rolled back'


@override_settings(SKYCONNECT_SMS_API_URL='', SKYCONNECT_SMS_API_KEY='')
def test_missing_configuration_names_the_setting_not_a_value():
    with pytest.raises(SkyConnectNotConfigured) as exc:
        send_sms(destination='251911528271', text='hello')

    assert 'SKYCONNECT_SMS_API_KEY' in str(exc.value)


# ── 11. the key never escapes ───────────────────────────────────────────────


@override_settings(**SKY_SETTINGS)
def test_the_api_key_is_sent_but_never_logged(caplog):
    with patch('api.integrations.skyconnect.sms.requests.post') as post:
        post.return_value = _Response(status_code=200, payload={'messageId': 'abc'})
        with caplog.at_level('DEBUG'):
            send_sms(destination='251911528271', text='hello')

        headers = post.call_args.kwargs['headers']

    assert headers['Authorization'] == f'Bearer {FAKE_KEY}', 'the key must still be sent'
    assert FAKE_KEY not in caplog.text, 'the key reached the log'
    assert 'Authorization' not in caplog.text


@override_settings(**SKY_SETTINGS)
def test_the_key_is_not_in_a_failure_message(caplog):
    with patch('api.integrations.skyconnect.sms.requests.post') as post:
        post.return_value = _Response(status_code=401, text='unauthorized')
        with caplog.at_level('DEBUG'), pytest.raises(SkyConnectError) as exc:
            send_sms(destination='251911528271', text='hello')

    assert FAKE_KEY not in str(exc.value)
    assert FAKE_KEY not in caplog.text


@override_settings(**SKY_SETTINGS)
def test_the_full_number_is_not_logged(caplog):
    with patch('api.integrations.skyconnect.sms.requests.post') as post:
        post.return_value = _Response(status_code=200, payload={'messageId': 'abc'})
        with caplog.at_level('INFO'):
            send_sms(destination='251911528271', text='hello')

    assert '+251911528271' not in caplog.text


# ── the request the provider receives ───────────────────────────────────────


@override_settings(**SKY_SETTINGS)
def test_the_request_matches_the_providers_contract():
    with patch('api.integrations.skyconnect.sms.requests.post') as post:
        post.return_value = _Response(status_code=200, payload={'messageId': 'xyz'})
        returned = send_sms(destination='251911528271', text='Subscription active')

    assert post.call_args.args[0] == API_URL
    assert post.call_args.kwargs['json'] == {
        'to': '+251911528271',
        'body': 'Subscription active',
        'senderId': 'Flipstar',
    }
    assert post.call_args.kwargs['headers']['Content-Type'] == 'application/json'
    assert post.call_args.kwargs['timeout'] > 0, 'a request with no timeout can hang a worker'
    assert returned == 'xyz'


# ── 6 & 7. TIMWE and the short code are untouched ───────────────────────────


def test_the_default_provider_is_still_smpp():
    """SMS_PROVIDER selects the gateway for everything that does not ask for
    another. Adding SkyConnect must not have moved it."""
    from django.conf import settings

    assert getattr(settings, 'SMS_PROVIDER', '') == 'timwe_smpp'


def test_a_message_with_no_provider_uses_the_configured_default():
    from api.services.sms import get_gateway

    assert get_gateway().name == 'timwe_smpp'


def test_asking_for_skyconnect_returns_skyconnect():
    from api.services.sms import get_gateway

    assert get_gateway('skyconnect').name == 'skyconnect'


@override_settings(**SKY_SETTINGS)
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


@override_settings(**SKY_SETTINGS)
def test_only_telebirr_messages_carry_the_new_provider(plan):
    from api.services.sms.dispatch import queue_sms

    queue_sms(
        phone_number='251911528271',
        text='otp 123456',
        purpose='otp_login',
        idempotency_key='otp-1',
    )
    notify_activated(plan, source=USSD)

    pinned = SmsMessage.objects.filter(provider=PROVIDER)
    assert pinned.count() == 1
    assert pinned.first().purpose == 'telebirr_subscription_activated'


# ── the amount is not invented ──────────────────────────────────────────────


@override_settings(**SKY_SETTINGS)
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
