"""
The gift endpoint's behaviour when the sender holds bonus coins.

The model-level rule is covered in test_bonus_coins_not_giftable.py. This is
the other half of the requirement: the backend is the final authority, so the
refusal has to survive a client that ignores every hint the UI gave it and
posts the request anyway.

What a rejected gift must leave behind
--------------------------------------
Nothing. No coins moved, no GiftTransaction row, and therefore no campaign
engagement -- gifts score ten points each, so a gift that was refused but still
recorded would pay its sender's recipient for a payment that never happened.
"""

import json

import fakeredis
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models import Reel
from api.models.contest import UserCoinBalance
from api.models.gift import Gift, GiftTransaction
from api.views.gift import PublicGiftViewSet
from common.security.e2e_encryption import decrypt_payload, encrypt_payload, generate_keypair
from infrastructure.keys import redis_store
from tests.conftest import grant_subscription

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


# The gift endpoint carries encrypted transport: the request body is a sealed
# envelope and the response comes back sealed too. Tests speak the same
# protocol rather than bypassing it, so what they exercise is the endpoint as
# a real client reaches it -- including the header check that runs before the
# view body.
@pytest.fixture
def server_keys(db):
    from infrastructure.keys import key_manager

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    yield key_manager.get_public_key()
    key_manager.reset()
    redis_store.reset_client()


@pytest.fixture
def client_keys():
    return generate_keypair()


def _decrypt(response, server_public_key, client_private_key):
    response.render()
    envelope = json.loads(response.content)
    if 'encrypted' not in envelope:
        # An error raised before the renderer sealed anything.
        return envelope
    plaintext = decrypt_payload(
        envelope['encrypted'],
        envelope['nonce'],
        server_public_key,
        envelope['checksum'],
        client_private_key,
    )
    return json.loads(plaintext)


@pytest.fixture
def sender():
    user = User.objects.create_user(username='sender', password='123456')
    grant_subscription(user)
    return user


@pytest.fixture
def recipient():
    return User.objects.create_user(username='receiver', password='123456')


@pytest.fixture
def gift():
    return Gift.objects.create(name='Rose', coin_value=50)


@pytest.fixture
def post(recipient):
    return Reel.objects.create(user=recipient, caption='hi', media='reels/x.mp4')


def set_balance(user, *, purchased=0, bonus=0, earned=0, airtime=0):
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        telebirr_purchased_balance=purchased,
        bonus_balance=bonus,
        earned_balance=earned,
        airtime_purchased_balance=airtime,
        purchased_balance=purchased + airtime,
        balance=purchased + bonus + earned + airtime,
    )
    balance.refresh_from_db()
    return balance


class Sent:
    """A response plus its decrypted body, so assertions read plainly."""

    def __init__(self, response, data):
        self.status_code = response.status_code
        self.data = data


@pytest.fixture
def send(sender, server_keys, client_keys):
    """Post a gift as `sender`, over the encrypted transport."""
    client_public_key, client_private_key = client_keys

    def _send(gift, recipient, post=None, quantity=1):
        body = {
            'gift_id': gift.id,
            'recipient_username': recipient.username,
            'quantity': quantity,
        }
        if post is not None:
            body['reel_id'] = post.id

        envelope = encrypt_payload(
            body,
            receiver_public_key_b64=server_keys,
            sender_private_key_b64=client_private_key,
        ).to_dict()

        request = factory.post(
            '/gifts/send/',
            data=json.dumps(envelope),
            content_type='application/json',
            HTTP_X_CLIENT_PUBLIC_KEY=client_public_key,
        )
        force_authenticate(request, user=sender)
        view = PublicGiftViewSet.as_view({'post': 'send'})
        response = view(request)
        return Sent(response, _decrypt(response, server_keys, client_private_key))

    return _send


# ---------------------------------------------------------------------------
# The refusal
# ---------------------------------------------------------------------------


def test_a_bonus_only_sender_is_refused(send, sender, gift, recipient):
    """0 purchased, 500 bonus, gift costs 50."""
    set_balance(sender, purchased=0, bonus=500)

    response = send(gift, recipient)

    assert response.status_code == 400, response.data


def test_the_refusal_carries_the_documented_code(send, sender, gift, recipient):
    """
    A machine-readable reason.

    The client has to tell "you cannot pay with these coins" apart from "you
    have no coins" -- the first offers Buy Coins, the second is the same
    offer for a different reason, and only one of them means the balance on
    screen is unusable rather than absent.
    """
    set_balance(sender, purchased=0, bonus=500)

    data = send(gift, recipient).data

    assert data['code'] == 'BONUS_COINS_NOT_ELIGIBLE_FOR_GIFT'
    assert data['success'] is False
    assert data['purchased_coins'] == 0
    assert data['bonus_coins'] == 500
    assert data['required_coins'] == 50
    assert 'bonus coins cannot be used' in data['message'].lower()


def test_nothing_is_deducted_when_the_gift_is_refused(send, sender, gift, recipient):
    set_balance(sender, purchased=0, bonus=500)

    send(gift, recipient)

    balance = UserCoinBalance.objects.get(user=sender)
    assert balance.bonus_balance == 500
    assert balance.balance == 500


def test_no_gift_row_is_created_when_refused(send, sender, gift, recipient):
    set_balance(sender, purchased=0, bonus=500)

    send(gift, recipient)

    assert GiftTransaction.objects.count() == 0


def test_a_refused_gift_earns_no_engagement(send, sender, gift, recipient, post):
    """
    Gifts are worth ten leaderboard points each.

    A refused gift that still counted would pay the recipient for a payment
    that never happened.
    """
    set_balance(sender, purchased=0, bonus=500)

    send(gift, recipient, post=post)

    from api.services.scoring.leaderboard import reel_engagement

    assert reel_engagement(post)['gifts'] == 0


def test_a_shortfall_is_not_topped_up_from_bonus(send, sender, gift, recipient):
    """20 purchased, 500 bonus, gift costs 50 -- refused, nothing moved."""
    set_balance(sender, purchased=20, bonus=500)

    response = send(gift, recipient)

    assert response.status_code == 400
    balance = UserCoinBalance.objects.get(user=sender)
    assert balance.telebirr_purchased_balance == 20
    assert balance.bonus_balance == 500
    assert GiftTransaction.objects.count() == 0


# ---------------------------------------------------------------------------
# The gift that should go through
# ---------------------------------------------------------------------------


def test_a_sender_with_enough_purchased_coins_succeeds(send, sender, gift, recipient, post):
    """100 purchased, 500 bonus, gift costs 50."""
    set_balance(sender, purchased=100, bonus=500)

    response = send(gift, recipient, post=post)

    assert response.status_code == 201, response.data
    assert GiftTransaction.objects.count() == 1


def test_a_successful_gift_spends_purchased_and_spares_bonus(send, sender, gift, recipient, post):
    set_balance(sender, purchased=100, bonus=500)

    send(gift, recipient, post=post)

    balance = UserCoinBalance.objects.get(user=sender)
    assert balance.telebirr_purchased_balance == 50
    assert balance.bonus_balance == 500, 'bonus coins were drawn into a gift'


def test_a_successful_gift_scores_ten_points(send, sender, gift, recipient, post):
    """The other side of the leaderboard rule: a real gift does count."""
    set_balance(sender, purchased=100, bonus=500)

    send(gift, recipient, post=post)

    from api.services.scoring.leaderboard import compute_score, reel_engagement

    counts = reel_engagement(post)
    assert counts['gifts'] == 1
    assert compute_score(counts) == 10


# ---------------------------------------------------------------------------
# The wallet a client reads before offering the button
# ---------------------------------------------------------------------------


def test_the_wallet_reports_bonus_and_giftable_separately(sender):
    """
    What the gift UI needs to disable its button honestly.

    Without a `giftable` figure the client has to re-derive which buckets may
    fund a gift, and any client that gets it wrong shows an enabled button
    over a balance the backend will refuse.
    """
    import fakeredis

    from common.security.e2e_encryption import generate_keypair
    from infrastructure.keys import key_manager, redis_store

    set_balance(sender, purchased=100, bonus=500, earned=20, airtime=30)

    redis_store.set_client(fakeredis.FakeRedis(decode_responses=True))
    key_manager.reset()
    key_manager.initialize()
    try:
        client_public_key, _ = generate_keypair()
        from rest_framework.test import APIRequestFactory, force_authenticate

        from api.views.wallet import wallet_summary

        request = APIRequestFactory().get('/wallet/', HTTP_X_CLIENT_PUBLIC_KEY=client_public_key)
        force_authenticate(request, user=sender)
        response = wallet_summary(request)

        assert response.status_code == 200, response.data
        block = response.data['balance']
        assert block['bonus'] == 500
        assert block['giftable'] == 100
        # Bonus stays out of `purchased`, so a client reading the old field
        # cannot mistake it for spendable-on-gifts.
        assert block['purchased'] == 130
    finally:
        key_manager.reset()
        redis_store.reset_client()
