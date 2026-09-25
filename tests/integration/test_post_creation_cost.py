"""
What posting costs, and that it is charged exactly once.

    image                        2 coins
    video under 60 seconds       2 coins
    video 60 seconds and over    100 coins

Charged in two places, because the duration is not known in the same breath as
the upload: the request charges the base 2 coins, and the worker adds the 98
difference once ffprobe has measured the file. That split is the security
property as much as an implementation detail -- **no number from the client is
ever read**, so a request claiming `duration=10` for a 100-second video is
charged as the 100-second video it is.

The boundary is the part these tests care most about. 59.9 seconds costs 2
coins and 60.0 costs 100, so the comparison being ``>=`` rather than ``>`` is
worth fifty times the price to whoever posts a one-minute video. It used to be
``>``.

Everything here uses the wallet the rest of the product uses:
``UserCoinBalance.spend_coins``, which refuses to go negative, and the
``CoinTransaction`` ledger every other charge is written to.
"""

import io
import os

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models import Reel
from api.models.contest import CoinTransaction, UserCoinBalance
from api.models.wallet import WalletConfig
from api.services import post_pricing
from api.tasks import media as media_tasks
from tests.conftest import grant_subscription

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()

MP4_HEADER = b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 64


@pytest.fixture(autouse=True)
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path / 'media')
    os.makedirs(settings.MEDIA_ROOT, exist_ok=True)
    settings.S3_BUCKET_NAME = ''
    return settings.MEDIA_ROOT


@pytest.fixture(autouse=True)
def no_welcome_bonus():
    """Accounts are created with a welcome bonus, which would make every
    balance assertion here about the bonus rather than the charge."""
    config = WalletConfig.get_config()
    config.welcome_bonus = 0
    config.save()


@pytest.fixture
def author(db):
    user = User.objects.create_user(username='cost_author', password='x')
    grant_subscription(user)
    return user


@pytest.fixture
def subscribed(monkeypatch):
    """Video posts are subscriber-only; that gate has its own tests."""
    import api.views.core as core

    monkeypatch.setattr(core, 'has_active_subscription', lambda user: True)


@pytest.fixture
def queued(monkeypatch):
    """What the request hands the worker, without running it."""
    calls = []
    monkeypatch.setattr(
        media_tasks.process_reel_media, 'delay', lambda *a, **k: calls.append((a, k))
    )
    return calls


def fund(user, coins):
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    if coins:
        balance.add_earned(coins, transaction_type='reward', description='test funding')
    balance.refresh_from_db()
    return balance


def balance_of(user):
    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    balance.refresh_from_db()
    return balance.balance


def jpeg_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (64, 48), (200, 80, 40)).save(buf, 'JPEG', quality=95)
    return buf.getvalue()


def upload(name, content, content_type):
    return SimpleUploadedFile(name, content, content_type=content_type)


def create(user, file, **data):
    from api.views.core import create_post

    request = factory.post('/posts/create/', {'file': file, **data})
    force_authenticate(request, user=user)
    return create_post(request)


def post_image(user, **data):
    return create(user, upload('photo.jpg', jpeg_bytes(), 'image/jpeg'), **data)


def post_video(user, **data):
    return create(user, upload('clip.mp4', MP4_HEADER, 'video/mp4'), **data)


def charges(user, *types):
    rows = CoinTransaction.objects.filter(user=user, coins__lt=0)
    if types:
        rows = rows.filter(transaction_type__in=types)
    return rows


def measure(reel, seconds):
    """What the worker does once ffprobe has told it the real duration."""
    media_tasks._charge_long_video(reel, seconds)
    reel.refresh_from_db()


# ── 1. an image post costs 2 ─────────────────────────────────────────────────


def test_an_image_post_deducts_two_coins(author, queued, django_capture_on_commit_callbacks):
    fund(author, 50)

    with django_capture_on_commit_callbacks(execute=True):
        response = post_image(author)

    assert response.status_code == 201, response.data
    assert balance_of(author) == 48


def test_each_image_post_is_charged(author, queued, django_capture_on_commit_callbacks):
    fund(author, 50)

    with django_capture_on_commit_callbacks(execute=True):
        post_image(author, client_upload_id='image-one-1')
        post_image(author, client_upload_id='image-two-2')
        post_image(author, client_upload_id='image-three-3')

    assert balance_of(author) == 44


def test_an_image_is_never_priced_as_a_video(author, queued, django_capture_on_commit_callbacks):
    """An image has no duration. Nothing may read one, or invent one."""
    fund(author, 200)

    with django_capture_on_commit_callbacks(execute=True):
        response = post_image(author, duration='90')

    reel = Reel.objects.get(pk=response.data['id'])
    measure(reel, 90)  # as if the worker ran the video path over it

    assert balance_of(author) == 198, 'charged as an image, twice over'
    assert reel.long_video_charged == 0


# ── 2-6. videos, and the boundary ────────────────────────────────────────────


@pytest.mark.parametrize('seconds', [1, 10, 30, 45, 59, 59.9])
def test_a_short_video_deducts_two_coins(
    author, subscribed, queued, django_capture_on_commit_callbacks, seconds
):
    fund(author, 200)

    with django_capture_on_commit_callbacks(execute=True):
        response = post_video(author)
    measure(Reel.objects.get(pk=response.data['id']), seconds)

    assert balance_of(author) == 198, f'{seconds}s should cost 2'


@pytest.mark.parametrize('seconds', [60, 60.0, 61, 90, 119, 120])
def test_a_long_video_deducts_one_hundred_coins(
    author, subscribed, queued, django_capture_on_commit_callbacks, seconds
):
    fund(author, 200)

    with django_capture_on_commit_callbacks(execute=True):
        response = post_video(author)
    measure(Reel.objects.get(pk=response.data['id']), seconds)

    assert balance_of(author) == 100, f'{seconds}s should cost 100'


def test_exactly_sixty_seconds_is_the_long_price(
    author, subscribed, queued, django_capture_on_commit_callbacks
):
    """The boundary, on its own, because it changed: 60.0 used to cost 2."""
    fund(author, 200)

    with django_capture_on_commit_callbacks(execute=True):
        response = post_video(author)
    measure(Reel.objects.get(pk=response.data['id']), 60.0)

    assert balance_of(author) == 100


@pytest.mark.parametrize(
    ('seconds', 'expected_balance', 'expected_cost'),
    [(59, 198, 2), (60, 100, 100), (90, 100, 100), (120, 100, 100)],
)
def test_the_boundary_prices_end_to_end(
    author,
    subscribed,
    queued,
    django_capture_on_commit_callbacks,
    seconds,
    expected_balance,
    expected_cost,
):
    """The four durations the product named, each charged through the real
    upload and the real surcharge."""
    fund(author, 200)

    with django_capture_on_commit_callbacks(execute=True):
        response = post_video(author)
    measure(Reel.objects.get(pk=response.data['id']), seconds)

    assert balance_of(author) == expected_balance, f'{seconds}s'
    assert sum(abs(row.coins) for row in charges(author)) == expected_cost


def test_the_band_itself():
    assert post_pricing.is_long_video(59.999) is False
    assert post_pricing.is_long_video(60) is True
    assert post_pricing.is_long_video(120) is True
    assert post_pricing.is_long_video(None) is False, 'unmeasured is not long'


# ── 7. beyond the limit: the existing rule decides ───────────────────────────


def test_the_accepted_maximum_is_two_minutes(settings):
    """The one number that decides what may be posted."""
    assert settings.MEDIA_MAX_VIDEO_SECONDS == 120


@pytest.mark.parametrize('seconds', [1, 30, 59, 60, 90, 119, 120, 119.99, 120.0])
def test_a_video_up_to_two_minutes_is_accepted(seconds):
    """Inclusive of the limit itself: 120.0 seconds is a video somebody may
    post, and is charged as a long one."""
    from api.tasks.media import _video_too_long

    assert _video_too_long(seconds) is False, f'{seconds}s was refused'


@pytest.mark.parametrize('seconds', [120.01, 120.5, 121, 150, 600])
def test_a_video_over_two_minutes_is_refused(seconds):
    """The smallest step past the limit is already too long."""
    from api.tasks.media import _video_too_long

    assert _video_too_long(seconds) is True, f'{seconds}s was accepted'


def test_the_limit_is_read_from_configuration_not_written_down(settings):
    """Raising or lowering the setting moves what is accepted, with no code
    change -- which is what keeps the recorder, the worker and the price band
    on one number."""
    from api.tasks.media import _video_too_long

    settings.MEDIA_MAX_VIDEO_SECONDS = 45

    assert _video_too_long(46) is True
    assert _video_too_long(45) is False


def test_an_unmeasured_duration_is_not_refused():
    """A file whose length could not be read is not called too long; the
    encode decides, as it did before."""
    from api.tasks.media import _video_too_long

    assert _video_too_long(0) is False
    assert _video_too_long(None) is False


def test_the_whole_priced_band_can_actually_be_posted(settings):
    """The band and the limit now agree: every video the price list covers is
    one the system accepts. This used to be false -- uploads stopped at 92
    while the band ran to 120, so 93-120 was priced and unreachable."""
    assert post_pricing.LONG_VIDEO_MAX_SECONDS == settings.MEDIA_MAX_VIDEO_SECONDS
    assert post_pricing.pricing_band_exceeds_upload_limit(settings.MEDIA_MAX_VIDEO_SECONDS) is False


# ── 8, 9, 12. not enough coins ───────────────────────────────────────────────


def test_too_few_coins_prevents_the_post(author, queued, django_capture_on_commit_callbacks):
    fund(author, 1)

    with django_capture_on_commit_callbacks(execute=True):
        response = post_image(author)

    assert response.status_code == 400
    assert response.data['code'] == 'INSUFFICIENT_COINS'
    assert not Reel.objects.filter(user=author).exists()


def test_too_few_coins_deducts_nothing(author, queued, django_capture_on_commit_callbacks):
    fund(author, 1)

    with django_capture_on_commit_callbacks(execute=True):
        post_image(author)

    assert balance_of(author) == 1
    assert not charges(author).exists()


def test_the_wallet_never_goes_negative(author, queued, django_capture_on_commit_callbacks):
    fund(author, 0)

    with django_capture_on_commit_callbacks(execute=True):
        post_image(author)

    assert balance_of(author) == 0


def test_a_long_video_is_not_given_away_when_the_surcharge_cannot_be_paid(
    author, subscribed, queued, django_capture_on_commit_callbacks
):
    """Two coins buys the upload, not the video: the worker fails the post
    rather than letting a 90-second video through unpaid."""
    from api.tasks.media import _Permanent

    fund(author, 2)
    with django_capture_on_commit_callbacks(execute=True):
        response = post_video(author)  # the base 2 is affordable
    assert response.status_code == 201, response.data
    assert balance_of(author) == 0

    reel = Reel.objects.get(pk=response.data['id'])
    with pytest.raises(_Permanent) as exc:
        media_tasks._charge_long_video(reel, 90)

    assert 'long_video_unpaid' in str(exc.value)
    assert balance_of(author) == 0, 'no coins conjured, none lost'


# ── 10. a failed post is not charged ─────────────────────────────────────────


def test_a_post_that_fails_to_be_created_is_not_charged(
    author, queued, monkeypatch, django_capture_on_commit_callbacks
):
    """The charge and the row are one transaction: if the row cannot be
    written, the coins are not taken."""
    fund(author, 50)

    def boom(*args, **kwargs):
        raise RuntimeError('database went away')

    monkeypatch.setattr(Reel.objects, 'create', boom)

    with django_capture_on_commit_callbacks(execute=True):
        response = post_image(author)

    assert response.status_code == 500
    assert balance_of(author) == 50
    assert not charges(author).exists()


def test_a_rejected_upload_is_not_charged(author, queued, django_capture_on_commit_callbacks):
    """Validation happens before any money moves."""
    fund(author, 50)

    with django_capture_on_commit_callbacks(execute=True):
        response = create(author, upload('notes.txt', b'plain text', 'text/plain'))

    assert response.status_code >= 400
    assert balance_of(author) == 50


# ── 11. a retry does not charge twice ────────────────────────────────────────


def test_a_retried_request_does_not_charge_again(
    author, queued, django_capture_on_commit_callbacks
):
    """The client sends the same upload id when a timeout makes it retry. The
    second request returns the post the first one made."""
    fund(author, 50)

    with django_capture_on_commit_callbacks(execute=True):
        first = post_image(author, client_upload_id='retry-me')
    with django_capture_on_commit_callbacks(execute=True):
        second = post_image(author, client_upload_id='retry-me')

    assert first.status_code == 201
    assert second.status_code == 200, 'the same post, not a new one'
    assert second.data['id'] == first.data['id']
    assert balance_of(author) == 48, 'charged once'
    assert Reel.objects.filter(user=author).count() == 1


def test_the_worker_running_twice_does_not_charge_the_video_twice(
    author, subscribed, queued, django_capture_on_commit_callbacks
):
    """Celery redelivers. `long_video_charged` is written in the same
    transaction as the debit, so the second run finds it already recorded."""
    fund(author, 200)
    with django_capture_on_commit_callbacks(execute=True):
        response = post_video(author)
    reel = Reel.objects.get(pk=response.data['id'])

    measure(reel, 90)
    measure(reel, 90)
    measure(reel, 90)

    assert balance_of(author) == 100
    assert charges(author, 'post_long_video').count() == 1


# ── 13. what the ledger records ──────────────────────────────────────────────


def test_the_charge_is_recorded_in_the_coin_history(
    author, queued, django_capture_on_commit_callbacks
):
    fund(author, 50)

    with django_capture_on_commit_callbacks(execute=True):
        post_image(author)

    row = charges(author).get()
    assert row.coins == -2
    assert row.transaction_type == 'post_create'
    assert 'post' in row.description.lower()


def test_a_long_video_records_both_halves(
    author, subscribed, queued, django_capture_on_commit_callbacks
):
    """2 then 98, because that is how they were charged -- and a person
    reading their history can see which was which."""
    fund(author, 200)
    with django_capture_on_commit_callbacks(execute=True):
        response = post_video(author)
    measure(Reel.objects.get(pk=response.data['id']), 90)

    rows = {row.transaction_type: row for row in charges(author)}
    assert rows['post_create'].coins == -2
    assert rows['post_long_video'].coins == -98
    assert sum(abs(row.coins) for row in rows.values()) == 100


# ── 18. the duration is the server's ─────────────────────────────────────────


def test_a_client_supplied_duration_changes_nothing(
    author, subscribed, queued, django_capture_on_commit_callbacks
):
    """The attack: claim 10 seconds for a 100-second video to pay 2 instead of
    100. The request never reads a duration -- the worker measures it."""
    fund(author, 200)

    with django_capture_on_commit_callbacks(execute=True):
        response = post_video(author, duration='10', video_duration='10', length='10')
    measure(Reel.objects.get(pk=response.data['id']), 100)

    assert balance_of(author) == 100, 'priced on the measured 100s, not the claimed 10s'


def test_nothing_in_the_charge_path_reads_a_request_duration():
    """A stricter statement of the same thing, so a future edit that starts
    trusting the client fails here rather than in production."""
    import inspect

    from api.services import post_pricing as pricing

    source = inspect.getsource(pricing)
    assert 'request' not in source.replace('# ', '').split('"""')[-1]


# ── the price list shown before posting ──────────────────────────────────────


def test_the_quote_matches_the_product_rule():
    config = WalletConfig.get_config()

    quote = post_pricing.quote(config)

    assert quote['image'] == 2
    assert quote['video_short'] == 2
    assert quote['video_long'] == 100
    assert quote['long_video_seconds'] == 60


def test_the_config_endpoint_publishes_the_price_list(encrypted_client_keys):
    """What the create screen reads, so the cost shown is the cost charged.

    Driven through the real encrypted transport (the endpoint sits behind it),
    so this cannot pass against a shape the browser never receives.
    """
    import json

    from django.urls import reverse
    from rest_framework.test import APIClient

    from common.security.e2e_encryption import decrypt_payload

    server_public_key, public, private = encrypted_client_keys
    user = User.objects.create_user(username='price_reader', password='x')
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(reverse('wallet-public-config'), HTTP_X_CLIENT_PUBLIC_KEY=public)
    assert response.status_code == 200, response.status_code
    response.render()
    body = json.loads(response.content)
    if {'encrypted', 'nonce', 'checksum'} <= body.keys():
        body = json.loads(
            decrypt_payload(
                body['encrypted'], body['nonce'], server_public_key, body['checksum'], private
            )
        )

    costs = body['post_costs']
    assert costs['image'] == 2
    assert costs['video_short'] == 2
    assert costs['video_long'] == 100


def test_the_total_is_the_sum_of_what_is_charged():
    """The quote and the two charges must agree, or the screen lies."""
    config = WalletConfig.get_config()

    base = post_pricing.base_cost(config, is_campaign_post=False)
    extra = post_pricing.long_video_extra(config, is_campaign_post=False)

    assert base == 2
    assert base + extra == post_pricing.total_cost(
        config, is_campaign_post=False, is_video=True, duration=90
    )
    assert post_pricing.total_cost(config, is_campaign_post=False, is_video=True, duration=30) == 2
