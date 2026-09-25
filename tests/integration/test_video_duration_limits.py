"""
How long a video each user may post.

    standard subscriber          60 seconds
    coin buyer / on-demand      120 seconds

What was there before: a single global ``MEDIA_MAX_VIDEO_SECONDS`` of 120,
so every subscriber could post the full two minutes, and a video of 60
seconds or more was simply charged more (api/services/post_pricing.py). The
price band stays; the ceiling is now per-user.

Where the rule actually lives
-----------------------------
In the worker, against the duration ffprobe measured. That is not a detail
-- it is the whole answer to "prevent bypass through direct API requests".
The upload endpoint has no duration to check: the pipeline deliberately does
not run FFmpeg in the request (api/services/media_pipeline.py), and a
``duration`` field in a request body is just a number a caller typed. Nothing
reads it. The file is measured, and the measurement decides.

So the bypass test here is not "does the endpoint reject a lie" -- it is
"does lying change anything", and the answer is no, because the claim is
never consulted.

The frontend limit is a courtesy that saves an upload, and is not tested
here; what is tested is that the number it displays comes from the server.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User

from api.services import video_limits

pytestmark = pytest.mark.django_db


@pytest.fixture
def subscriber(db):
    """A user with a subscription and no coin purchases."""
    return User.objects.create_user(username='standard_sub', password='x')


@pytest.fixture
def coin_buyer(db):
    """A user who has bought coins."""
    user = User.objects.create_user(username='coin_buyer', password='x')
    buy_coins(user, 100)
    return user


def buy_coins(user, amount, payment_method='telebirr'):
    """A real purchase, through the wallet that records them.

    add_purchased writes the CoinTransaction that video_limits reads, so the
    entitlement is earned the same way a real one is rather than asserted.
    """
    from api.models.contest import UserCoinBalance

    balance, _ = UserCoinBalance.objects.get_or_create(user=user)
    balance.add_purchased(amount, payment_method=payment_method)
    return balance


# ── the two limits ──────────────────────────────────────────────────────────


def test_a_standard_subscriber_gets_sixty_seconds(subscriber):
    assert video_limits.max_video_seconds(subscriber) == 60


def test_a_coin_buyer_gets_one_hundred_and_twenty_seconds(coin_buyer):
    assert video_limits.max_video_seconds(coin_buyer) == 120


def test_the_documented_figures(subscriber):
    assert video_limits.STANDARD_MAX_SECONDS == 60
    assert video_limits.EXTENDED_MAX_SECONDS == 120


def test_buying_coins_unlocks_the_longer_limit(subscriber):
    """The requirement's wording: the extended duration is unlocked by the
    qualifying coin purchase."""
    assert video_limits.max_video_seconds(subscriber) == 60

    buy_coins(subscriber, 50)

    assert video_limits.max_video_seconds(subscriber) == 120


def test_spending_the_coins_does_not_take_the_limit_away(coin_buyer):
    """Having bought is what qualifies, not still holding.

    A limit that rose and fell with a balance would be incomprehensible to
    the person it applied to.
    """
    from api.models.contest import UserCoinBalance

    balance = UserCoinBalance.objects.get(user=coin_buyer)
    balance.spend_coins(balance.balance, transaction_type='boost')

    assert video_limits.max_video_seconds(coin_buyer) == 120


def test_airtime_coins_qualify_too(subscriber):
    """A purchase is a purchase, whichever rail it was paid on."""
    buy_coins(subscriber, 50, payment_method='airtime')

    assert video_limits.max_video_seconds(subscriber) == 120


def test_reward_coins_do_not_qualify(subscriber):
    """Earned coins are not a purchase. Otherwise the extended limit could be
    farmed rather than bought, which is the opposite of what it is for."""
    from api.models.contest import UserCoinBalance

    balance, _ = UserCoinBalance.objects.get_or_create(user=subscriber)
    balance.add_earned(500, transaction_type='reward')

    assert video_limits.max_video_seconds(subscriber) == 60


def test_a_bonus_does_not_qualify(subscriber):
    from api.models.contest import UserCoinBalance

    balance, _ = UserCoinBalance.objects.get_or_create(user=subscriber)
    balance.add_bonus(500)

    assert video_limits.max_video_seconds(subscriber) == 60


def test_an_ondemand_subscription_qualifies(subscriber):
    """The on-demand tier buys its coins outright, so its holders are coin
    buyers by definition."""
    from django.utils import timezone

    from api.models import SubscriptionTier
    from api.models.subscription import SubscriptionPlan

    tier = SubscriptionTier.objects.filter(duration_type='ondemand').first()
    if tier is None:
        pytest.skip('no on-demand tier seeded')

    SubscriptionPlan.objects.create(
        user=subscriber,
        tier=tier,
        status='active',
        duration_type='ondemand',
        start_date=timezone.now(),
        end_date=timezone.now() + timezone.timedelta(days=30),
    )

    assert video_limits.max_video_seconds(subscriber) == 120


def test_a_non_subscriber_gets_the_standard_limit(db):
    """Posting a video needs a subscription at all -- enforced separately in
    api/services/subscription_access.py and covered by
    test_video_post_subscription_gate.py. The duration rule does not grant
    anybody the longer limit for lacking one."""
    nobody = User.objects.create_user(username='no_sub', password='x')

    assert video_limits.max_video_seconds(nobody) == 60


def test_an_anonymous_user_gets_no_extension():
    from django.contrib.auth.models import AnonymousUser

    assert video_limits.max_video_seconds(AnonymousUser()) == 60


# ── the boundary ────────────────────────────────────────────────────────────


@pytest.mark.parametrize('duration', [1, 30, 59.9, 60, 60.0])
def test_sixty_seconds_and_under_is_allowed_for_a_subscriber(subscriber, duration):
    """Inclusive of 60, matching the pricing boundary so that '60 seconds'
    means one thing across the product."""
    assert not video_limits.exceeds_limit(duration, subscriber)


@pytest.mark.parametrize('duration', [60.01, 61, 90, 119, 120, 300])
def test_over_sixty_seconds_is_refused_for_a_subscriber(subscriber, duration):
    assert video_limits.exceeds_limit(duration, subscriber)


@pytest.mark.parametrize('duration', [60.01, 90, 119.9, 120, 120.0])
def test_up_to_two_minutes_is_allowed_for_a_coin_buyer(coin_buyer, duration):
    assert not video_limits.exceeds_limit(duration, coin_buyer)


@pytest.mark.parametrize('duration', [120.01, 121, 180, 600])
def test_over_two_minutes_is_refused_even_for_a_coin_buyer(coin_buyer, duration):
    """The extended limit is a limit, not an exemption."""
    assert video_limits.exceeds_limit(duration, coin_buyer)


def test_an_unmeasured_duration_is_not_refused(subscriber):
    """Refusing a video because probing failed would turn an encoding
    problem into an accusation."""
    for unknown in (None, 0, ''):
        assert not video_limits.exceeds_limit(unknown, subscriber)


def test_the_deployment_ceiling_still_caps_everybody(coin_buyer, settings):
    """No entitlement exceeds MEDIA_MAX_VIDEO_SECONDS: it is what the
    encoding and storage budget can take."""
    settings.MEDIA_MAX_VIDEO_SECONDS = 45

    assert video_limits.max_video_seconds(coin_buyer) == 45
    assert video_limits.exceeds_limit(50, coin_buyer)


def test_a_configured_minimum_purchase_can_be_required(subscriber, settings):
    """'The required qualifying coin purchase' is a commercial decision, so
    it is tunable without a deploy."""
    settings.VIDEO_EXTENDED_MIN_PURCHASED_COINS = 500

    buy_coins(subscriber, 100)
    assert video_limits.max_video_seconds(subscriber) == 60, 'too small a purchase qualified'

    buy_coins(subscriber, 400)
    assert video_limits.max_video_seconds(subscriber) == 120


# ── the worker is what enforces it ──────────────────────────────────────────


def test_the_worker_refuses_a_video_over_the_users_limit(subscriber, coin_buyer):
    """The check the pipeline actually runs, against a measured duration."""
    from api.tasks.media import _video_too_long

    assert _video_too_long(90, subscriber)
    assert not _video_too_long(90, coin_buyer)


def test_the_worker_falls_back_to_the_global_ceiling_without_a_user(settings):
    """A backfill of old posts applies the rule that published them, not a
    limit its author never had."""
    from api.tasks.media import _video_too_long

    settings.MEDIA_MAX_VIDEO_SECONDS = 120

    assert not _video_too_long(90, None)
    assert _video_too_long(121, None)


def test_a_claimed_duration_in_the_request_changes_nothing(subscriber):
    """The bypass attempt, and why it is not one.

    Nothing anywhere reads a client-supplied duration -- the upload request
    has no duration at all, and the worker measures the file. So there is no
    field to lie in: a request claiming 10 seconds for a 90-second video is
    refused on the 90 that ffprobe returned.
    """
    from api.tasks.media import _video_too_long

    claimed, measured = 10, 90.0

    assert not video_limits.exceeds_limit(claimed, subscriber)
    assert _video_too_long(measured, subscriber), 'the measurement is what decides'


def test_the_upload_path_never_reads_a_duration_field():
    """Asserted against the source, because the protection *is* the absence.

    If an endpoint ever starts trusting request.data['duration'], the bypass
    becomes real and every test above would still pass.
    """
    import inspect

    from api.services import media_pipeline
    from api.views import campaign_user, core

    for module in (media_pipeline, core, campaign_user):
        source = inspect.getsource(module)
        for claim in ("data.get('duration'", 'data.get("duration"', "data['duration']"):
            assert claim not in source, f'{module.__name__} reads a client duration'


# ── what the client is told ─────────────────────────────────────────────────


def test_the_limit_is_published_for_the_create_screen(subscriber):
    payload = video_limits.limits_for(subscriber)

    assert payload['max_video_seconds'] == 60
    assert payload['standard_max_seconds'] == 60
    assert payload['extended_max_seconds'] == 120
    assert payload['extended_unlocked'] is False
    assert payload['extended_requires']


def test_a_coin_buyer_is_told_their_limit_is_unlocked(coin_buyer):
    payload = video_limits.limits_for(coin_buyer)

    assert payload['max_video_seconds'] == 120
    assert payload['extended_unlocked'] is True
    assert payload['extended_requires'] is None


def test_the_refusal_says_how_to_lift_the_limit(subscriber):
    """A refusal that does not say what would have worked is just a wall."""
    message = video_limits.too_long_message(subscriber)

    assert '60' in message
    assert '120' in message
    assert 'coin' in message.lower()


def test_a_coin_buyer_is_not_told_to_buy_coins(coin_buyer):
    message = video_limits.too_long_message(coin_buyer)

    assert '120' in message
    assert 'Buy coins' not in message


def config_body(user, keys):
    """What /wallet/config/ actually answers this user.

    The endpoint is end-to-end encrypted, so the body comes back sealed to
    the client's key; the same helper shape test_airtime_purchase_enabled.py
    uses against this endpoint.
    """
    import json

    from django.urls import reverse
    from rest_framework.test import APIClient

    from common.security.e2e_encryption import decrypt_payload

    server_public_key, public, private = keys
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
    return body


def test_the_wallet_config_endpoint_carries_the_limit(subscriber, encrypted_client_keys):
    """Where the create screen reads it from, alongside the post prices it
    already fetches."""
    body = config_body(subscriber, encrypted_client_keys)

    assert body['video_limits']['max_video_seconds'] == 60
    assert body['video_limits']['extended_unlocked'] is False


def test_the_endpoint_answers_per_user(subscriber, coin_buyer, encrypted_client_keys):
    """Two accounts, two answers -- the limit is not a global constant the
    client can cache once and reuse for everybody."""
    standard = config_body(subscriber, encrypted_client_keys)
    buyer = config_body(coin_buyer, encrypted_client_keys)

    assert standard['video_limits']['max_video_seconds'] == 60
    assert buyer['video_limits']['max_video_seconds'] == 120


def test_a_rejected_post_explains_itself(subscriber):
    """processing_error is a code; the message beside it is what a person
    reads, and it has to state the limit that applied to them."""
    from api.views.core import _processing_error_message

    class Post:
        processing_error = 'video_too_long'

    message = _processing_error_message(Post(), subscriber)

    assert message and '60' in message


def test_other_failures_stay_codes(subscriber):
    """A storage fault is not something to explain to whoever happened to
    upload during it."""
    from api.views.core import _processing_error_message

    class Post:
        processing_error = 'storage_unavailable'

    assert _processing_error_message(Post(), subscriber) is None


# ── the pricing band is unchanged ───────────────────────────────────────────


def test_the_long_video_price_band_still_starts_at_sixty():
    """This work added a ceiling; it did not move the price boundary."""
    from api.services import post_pricing

    assert post_pricing.LONG_VIDEO_SECONDS == 60
    assert post_pricing.is_long_video(60)
    assert not post_pricing.is_long_video(59.9)


def test_a_coin_buyers_long_video_is_still_charged(coin_buyer):
    """The extended limit lets the video exist. It does not make it free."""
    from api.services import post_pricing

    assert not video_limits.exceeds_limit(90, coin_buyer)
    assert post_pricing.is_long_video(90)


# ── campaign uploads ────────────────────────────────────────────────────────


def test_a_campaign_entry_is_capped_by_the_same_rule(subscriber):
    """One duration rule, whichever endpoint the upload came through."""
    from api.tasks.media import _video_too_long

    assert _video_too_long(90, subscriber)


def campaign_post_source():
    """The view's own source.

    ``inspect.getsource`` on the decorated name returns DRF's wrapper, not
    the function -- the module file is read instead and the one function
    sliced out of it.
    """
    from pathlib import Path

    from api.views import campaign_user

    text = Path(campaign_user.__file__).read_text(encoding='utf-8')
    start = text.index('def create_campaign_post(')
    end = text.index('\ndef ', start)
    return text[start:end]


def test_the_campaign_daily_limit_is_enforced_at_upload():
    """One post or video a day per campaign, checked before the file is
    stored or charged. Covered in full by test_campaign_eligibility.py;
    pinned here so the video rules and the campaign rules are known to meet
    in the same endpoint."""
    source = campaign_post_source()

    assert 'daily_entry_refusal' in source
    assert source.index('daily_entry_refusal') < source.index(
        'charge_engagement'
    ), 'a refused second entry must be refused before it is charged'


def test_a_campaign_entry_is_charged_and_tracked():
    """The other two campaign requirements, at the same call site."""
    source = campaign_post_source()

    assert 'charge_engagement' in source, 'campaign uploads are not charged'
    assert 'PostScore.objects.create' in source, 'campaign uploads are not tracked'


def test_eligibility_counts_the_entry_that_was_made(subscriber):
    """The tracking that matters: a campaign upload is what eligibility is
    computed from."""
    from datetime import timedelta

    from django.utils import timezone

    from api.models import Reel
    from api.models.campaign import Campaign
    from api.models.campaign_extended import PostScore
    from api.services import campaign_eligibility

    start = timezone.now() - timedelta(days=1)
    campaign = Campaign.objects.create(
        title='Daily Sprint',
        campaign_type='daily',
        status='active',
        start_date=start,
        entry_deadline=timezone.now() + timedelta(hours=1),
    )
    reel = Reel.objects.create(user=subscriber, caption='entry', is_campaign_post=True)
    PostScore.objects.create(
        reel=reel, campaign=campaign, user=subscriber, moderation_status='approved'
    )

    assert campaign_eligibility.days_posted(subscriber, campaign=campaign) == 1
    assert not campaign_eligibility.can_enter_today(subscriber, campaign)


# ── the worker still does everything else it did ────────────────────────────


def test_the_upload_request_still_does_not_run_ffmpeg():
    """The pipeline's defining property, and the reason the duration check
    lives in the worker. A probe added to the request would put FFmpeg back
    on the request path for every upload.

    Checked against what the module *runs*, not what it mentions: its
    docstring says the word while explaining that it does not do it.
    """
    import inspect

    from api.services import media_pipeline

    code = [
        line
        for line in inspect.getsource(media_pipeline).splitlines()
        if not line.lstrip().startswith('#')
    ]
    body = '\n'.join(code).lower()

    assert 'subprocess' not in body, 'the upload request shells out'
    for call in ("run('ffprobe", 'run("ffprobe', "run('ffmpeg", 'run("ffmpeg'):
        assert call not in body, 'FFmpeg is back on the request path'


def test_the_duration_check_runs_before_and_after_encoding():
    """Both call sites pass the user. One left on the global limit would let
    a too-long video through whichever side it was on."""
    import inspect

    from api.tasks import media

    source = inspect.getsource(media)
    checks = [
        line for line in source.splitlines() if '_video_too_long(' in line and 'def ' not in line
    ]

    assert len(checks) >= 2, 'the check is no longer made on both sides of encoding'
    for line in checks:
        assert 'reel.user' in line, f'a duration check ignores whose video it is: {line.strip()}'


def test_a_rejected_video_is_recorded_as_failed_not_published(subscriber):
    """The refusal path: _Permanent('video_too_long') reaches _give_up, which
    marks the post FAILED with that code rather than serving it."""
    import inspect

    from api.tasks import media

    source = inspect.getsource(media)

    assert "_Permanent('video_too_long')" in source
    with patch.object(media, '_finish') as finish:
        media._give_up(1, 'task', 'video_too_long', live=False)

    assert finish.called
    assert finish.call_args.kwargs['processing_error'] == 'video_too_long'
