"""
Setting a PIN after subscribing by telebirr USSD push.

That flow has no registration step. It creates the account itself, with
``password=None`` (api/views/subscription.py), and nothing ever asks the
subscriber to choose a PIN. So they arrive at the login screen with an account
they cannot log into, and every route forward used to be a dead end:

* the PIN form said **"Invalid password"** -- untrue, there is no password to
  get wrong, and it invites them to keep guessing;
* Sign up said **"Phone number already registered"**, because it is;
* only "Forgot PIN?" worked, which nobody clicks having never set one.

Nothing new was built for this. The PIN reset already sends an OTP to the
number and sets a PIN on the existing account, and it is properly guarded --
it requires an active subscription and a real code. What was missing was a
signal saying "you have no PIN", so a client can take the subscriber straight
there. These pin that signal, and that it never leaks whether a stranger's
number has an account.
"""

import json

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient

from api.models import UserProfile
from common.security.e2e_encryption import decrypt_payload, encrypt_payload

pytestmark = pytest.mark.django_db

PHONE = '251911528271'


@pytest.fixture(autouse=True)
def _forget_earlier_attempts():
    """Start each test with a clean rate limiter.

    Signing in is throttled, and the limiter's counters live in a cache shared
    by the whole run. Without this a test inherits the previous one's failed
    attempts and is answered 429 instead of the thing it is asserting about --
    so it fails for a reason that has nothing to do with what it checks.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def ussd_subscriber(db):
    """An account as the USSD purchase flow creates one: no usable password."""
    user = User.objects.create_user(username='user_11528271', password=None)
    profile = user.profile
    profile.phone_number = PHONE
    profile.save(update_fields=['phone_number'])
    return user


@pytest.fixture
def pin_holder(db):
    user = User.objects.create_user(username='has_a_pin', password='123456')
    profile = user.profile
    profile.phone_number = '251911000222'
    profile.save(update_fields=['phone_number'])
    return user


@pytest.fixture
def attempt_login(encrypted_client_keys):
    """Sign in through the real transport.

    The endpoint is behind @encrypted_endpoint, so both the header and an
    encrypted body are required. A plain POST is refused with a 400 before the
    login logic runs -- which is exactly how the first version of these tests
    managed to look like it was asserting something while it was only
    exercising the encryption gate.
    """
    server_public_key, public, private = encrypted_client_keys

    def _login(phone, pin):
        # The body is sealed too, not just the response: the parser rejects
        # plaintext before the view runs, so a plain POST never reaches the
        # login logic at all.
        sealed = encrypt_payload({'phone': phone, 'password': pin}, server_public_key, private)
        client = APIClient()
        response = client.post(
            reverse('auth-login-with-phone'),
            sealed.to_dict(),
            format='json',
            HTTP_X_CLIENT_PUBLIC_KEY=public,
        )
        response.render()
        raw = json.loads(response.content)
        if isinstance(raw, dict) and {'encrypted', 'nonce', 'checksum'} <= raw.keys():
            raw = json.loads(
                decrypt_payload(
                    raw['encrypted'], raw['nonce'], server_public_key, raw['checksum'], private
                )
            )
        return response.status_code, raw

    return _login


def test_a_subscriber_with_no_pin_is_told_so_not_that_their_pin_is_wrong(
    ussd_subscriber, attempt_login
):
    status, body = attempt_login(PHONE, '123456')

    assert status == 403, body
    assert body['code'] == 'pin_not_set'
    assert body['requires_pin_setup'] is True
    assert 'invalid' not in body['error'].lower(), body['error']


def test_the_response_carries_the_number_so_the_client_can_continue(ussd_subscriber, attempt_login):
    _, body = attempt_login(PHONE, '000000')

    assert body['phone'] == PHONE


def test_any_pin_gets_the_same_answer_because_none_is_right(ussd_subscriber, attempt_login):
    from django.core.cache import cache

    for pin in ('123456', '000000', 'whatever'):
        cache.clear()  # the limiter is not what this test is about
        assert attempt_login(PHONE, pin)[1]['code'] == 'pin_not_set', pin


def test_an_account_with_a_pin_still_gets_a_wrong_pin_error(pin_holder, attempt_login):
    """The new answer must not swallow a genuine mistyped PIN."""
    status, body = attempt_login('251911000222', '999999')

    assert status == 401, body
    assert body.get('code') != 'pin_not_set'


def test_the_right_pin_still_logs_in(pin_holder, attempt_login):
    status, body = attempt_login('251911000222', '123456')

    assert status == 200, body
    assert body['token']


def test_an_unknown_number_is_not_told_whether_an_account_exists(db, attempt_login):
    """`pin_not_set` says an account exists for this number. It must only be
    said to numbers that really have one, or it becomes a way to enumerate
    subscribers."""
    status, body = attempt_login('251911999888', '123456')

    assert body.get('code') != 'pin_not_set'
    assert status == 400, body
    assert 'no account' in body['error'].lower(), body['error']


def test_setting_a_pin_makes_the_account_usable(ussd_subscriber, attempt_login):
    """The reset path is what the signal points at: after it, the ordinary PIN
    login works. Called directly here -- the OTP itself is covered by the OTP
    tests, and this is about the account ending up usable."""
    ussd_subscriber.set_password('654321')
    ussd_subscriber.save()

    assert attempt_login(PHONE, '654321')[0] == 200


def test_the_account_really_starts_without_a_password(ussd_subscriber):
    """If the purchase flow ever starts setting one, this whole signal is
    unnecessary and should be revisited."""
    assert ussd_subscriber.has_usable_password() is False
    assert UserProfile.objects.get(user=ussd_subscriber).phone_number == PHONE
