"""
What happens to the balance when a withdrawal does not get paid.

A withdrawal takes the user's points the moment it is requested -- see
`api/views/wallet.py::request_withdrawal`, "Deduct points now (refunded if
rejected)". Three endings never pay the money out: an admin rejects it, the
user cancels it, or the automatic payout cannot be started. All three have to
give the points back, and two of them did not.

Both bugs had the same shape. The refund was written against `coin_amount`,
the legacy field, which the points flow never sets -- so the refund ran,
reported success, wrote a zero-coin transaction and moved nothing. The
withdrawal ended as 'rejected' or 'cancelled' and the user's points were
simply gone. Nothing failed, so nothing showed up anywhere.

These tests are about money, so they assert on the balance in the database
after the real endpoint has run, not on the refund helper in isolation.
"""

import json

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models.contest import UserCoinBalance
from api.models.wallet import WithdrawalRequest
from common.security.e2e_encryption import decrypt_payload

pytestmark = pytest.mark.django_db

STARTING_POINTS = 5000
WITHDRAWN = 1200


@pytest.fixture
def subscriber():
    user = User.objects.create_user(username='withdrawer', password='x')
    profile = user.profile
    profile.points = STARTING_POINTS
    profile.points_withdrawn_total = WITHDRAWN
    profile.save(update_fields=['points', 'points_withdrawn_total'])
    return user


@pytest.fixture
def staff():
    return User.objects.create_user(username='payouts_admin', password='x', is_staff=True)


def make_withdrawal(user, *, points=WITHDRAWN, coins=0, status='pending'):
    """A withdrawal as request_withdrawal creates one: points already taken."""
    return WithdrawalRequest.objects.create(
        user=user,
        point_amount=points,
        coin_amount=coins,
        gross_birr=120,
        fee_birr=20,
        net_birr=100,
        conversion_rate=10,
        payout_method='telebirr',
        payout_account='0912345678',
        status=status,
    )


def points_of(user):
    user.profile.refresh_from_db()
    return user.profile.points


def reject(staff_user, withdrawal, notes='account details do not match'):
    client = APIClient()
    # A real token in the header, not force_authenticate: /api/v1/admin/ is
    # guarded by AdminPathGuardMiddleware, which resolves the user itself --
    # from the session or an `Authorization: Token ...` header -- before DRF's
    # authentication ever runs, so it cannot see a forced one. Going through
    # the guard is the point: it is on the path a real rejection takes.
    token, _ = Token.objects.get_or_create(user=staff_user)
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client.post(
        reverse('admin-withdrawal-action', args=[withdrawal.id]),
        {'action': 'reject', 'notes': notes},
        format='json',
    )


def cancel(user, withdrawal, keys):
    """The user's own cancel endpoint, which speaks the encrypted transport.

    `keys` is tests/conftest.py's `encrypted_client_keys`: the server keypair
    in an in-memory Redis, plus this client's pair.
    """
    server_public_key, public, private = keys
    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        reverse('wallet-cancel-withdrawal', args=[withdrawal.id]),
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


# ── rejection ───────────────────────────────────────────────────────────────


def test_rejecting_a_withdrawal_gives_the_points_back(subscriber, staff):
    withdrawal = make_withdrawal(subscriber)

    assert reject(staff, withdrawal).status_code == 200

    withdrawal.refresh_from_db()
    assert withdrawal.status == 'rejected'
    assert points_of(subscriber) == STARTING_POINTS + WITHDRAWN


def test_rejecting_a_legacy_coin_withdrawal_still_returns_the_coins(subscriber, staff):
    """Old rows carry coins rather than points, and must keep working."""
    balance, _ = UserCoinBalance.objects.get_or_create(user=subscriber)
    before = balance.earned_balance or 0
    withdrawal = make_withdrawal(subscriber, points=0, coins=300)

    assert reject(staff, withdrawal).status_code == 200

    balance.refresh_from_db()
    assert balance.earned_balance == before + 300
    assert points_of(subscriber) == STARTING_POINTS, 'points were not involved'


def test_a_second_rejection_cannot_refund_again(subscriber, staff):
    withdrawal = make_withdrawal(subscriber)

    assert reject(staff, withdrawal).status_code == 200
    second = reject(staff, withdrawal)

    assert second.status_code == 400, 'a rejected withdrawal was rejected again'
    assert points_of(subscriber) == STARTING_POINTS + WITHDRAWN, 'refunded twice'


def test_rejection_tells_the_user_the_points_are_back(subscriber, staff):
    """The message promises a refund, so the refund has to have happened --
    these two were out of step before: the text said the points were not
    coming back, because they were not."""
    from api.models import SmsMessage

    withdrawal = make_withdrawal(subscriber)
    subscriber.profile.phone_number = '251911528271'
    subscriber.profile.save(update_fields=['phone_number'])

    assert reject(staff, withdrawal).status_code == 200

    sms = SmsMessage.objects.filter(purpose='withdrawal_failed').first()
    assert sms is not None, 'no message was queued'
    assert 'returned to your balance' in sms.body, sms.body
    assert str(WITHDRAWN) in sms.body, sms.body
    assert 'contact Flipstar support' not in sms.body, 'told to chase a refund that happened'


# ── cancellation by the user ────────────────────────────────────────────────


def test_cancelling_a_withdrawal_gives_the_points_back(subscriber, encrypted_client_keys):
    withdrawal = make_withdrawal(subscriber)

    code, body = cancel(subscriber, withdrawal, encrypted_client_keys)

    assert code == 200, body
    withdrawal.refresh_from_db()
    assert withdrawal.status == 'cancelled'
    assert points_of(subscriber) == STARTING_POINTS + WITHDRAWN


def test_the_cancel_response_reports_the_points_it_returned(subscriber, encrypted_client_keys):
    """The screen reads new_balance; reporting only coins left the number on
    it unchanged after a refund that did happen."""
    withdrawal = make_withdrawal(subscriber)

    _, body = cancel(subscriber, withdrawal, encrypted_client_keys)

    assert body['new_balance']['points'] == STARTING_POINTS + WITHDRAWN


def test_cancelling_twice_refunds_once(subscriber, encrypted_client_keys):
    withdrawal = make_withdrawal(subscriber)

    first, _ = cancel(subscriber, withdrawal, encrypted_client_keys)
    second, body = cancel(subscriber, withdrawal, encrypted_client_keys)

    assert first == 200
    assert second == 400, 'a cancelled withdrawal was cancelled again'
    assert points_of(subscriber) == STARTING_POINTS + WITHDRAWN, 'refunded twice'


def test_an_approved_withdrawal_cannot_be_cancelled(subscriber, encrypted_client_keys):
    """Money may already be moving; only a pending one is the user's to take
    back."""
    withdrawal = make_withdrawal(subscriber, status='approved')

    code, _ = cancel(subscriber, withdrawal, encrypted_client_keys)

    assert code == 400
    assert points_of(subscriber) == STARTING_POINTS


def test_one_user_cannot_cancel_another_users_withdrawal(subscriber, encrypted_client_keys):
    other = User.objects.create_user(username='someone_else', password='x')
    withdrawal = make_withdrawal(subscriber)

    code, _ = cancel(other, withdrawal, encrypted_client_keys)

    assert code == 404
    withdrawal.refresh_from_db()
    assert withdrawal.status == 'pending'
    assert points_of(subscriber) == STARTING_POINTS


# ── what the refund deliberately does not do ────────────────────────────────


def test_the_lifetime_withdrawn_total_is_not_wound_back(subscriber, staff):
    """Documented, not accidental: `points_withdrawn_total` only ever goes up,
    and the automatic payout path made the same choice. It therefore counts
    withdrawals that were never paid. Pinned here so that changing it is a
    decision somebody makes rather than a side effect."""
    withdrawal = make_withdrawal(subscriber)

    reject(staff, withdrawal)

    subscriber.profile.refresh_from_db()
    assert subscriber.profile.points_withdrawn_total == WITHDRAWN


def test_a_withdrawal_that_took_nothing_refunds_nothing(subscriber, staff):
    withdrawal = make_withdrawal(subscriber, points=0, coins=0)

    assert reject(staff, withdrawal).status_code == 200

    assert points_of(subscriber) == STARTING_POINTS
