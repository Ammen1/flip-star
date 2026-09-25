"""
Who may do what, without a subscription.

    allowed      sign up, sign in, browse, view
    refused      post, upload video, like, share, comment, enter a campaign

What the audit found
--------------------
Only **video** was gated. ``_create_post_from_upload`` checked the
subscription under ``if is_video``, and liking, sharing, commenting and
entering a campaign checked nothing at all -- they charged coins and let the
action through.

The charge was not standing in for the gate either, and this is the part
worth being precise about: a new account is given a welcome bonus
(``WalletConfig.welcome_bonus``, 100 coins by default), so a non-subscriber
had coins. Liking costs 1. They could like ninety-nine more times before
anything stopped them, and sharing, commenting and posting images were open
the whole time.

So these tests are not about a rule that existed and drifted. They are about
five rules that were not enforced anywhere but the client.

Reading and writing
-------------------
Reading stays open, deliberately: the requirement wants non-subscribers to
browse and view, which is how anybody decides to subscribe. Every refusal
below is a write.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models import Reel
from api.models.core import Subscription
from api.services.subscription_access import (
    SUBSCRIPTION_REQUIRED_CODE,
    has_active_subscription,
    subscriber_action_refusal,
)

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()

MP4 = b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 64


def jpeg_bytes(width=64, height=48):
    """A real, decodable JPEG.

    It has to decode: media validation runs before the subscription check,
    so an unreadable file is refused as unreadable and never reaches the
    gate these tests are about.
    """
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new('RGB', (width, height), (200, 80, 40)).save(buffer, format='JPEG')
    return buffer.getvalue()


# ── accounts in each state ──────────────────────────────────────────────────


@pytest.fixture
def nobody(db):
    """Signed in, no subscription. What most of this file is about."""
    return User.objects.create_user(username='no_plan', password='x')


@pytest.fixture
def subscriber(db):
    user = User.objects.create_user(username='has_plan', password='x')
    Subscription.objects.update_or_create(
        user=user,
        defaults={'plan': 'pro', 'expires_at': timezone.now() + timedelta(days=30)},
    )
    return user


@pytest.fixture
def expired(db):
    user = User.objects.create_user(username='lapsed', password='x')
    Subscription.objects.update_or_create(
        user=user,
        defaults={'plan': 'pro', 'expires_at': timezone.now() - timedelta(days=1)},
    )
    return user


@pytest.fixture
def pending(db):
    """Paid, not yet confirmed. A plan row exists but is not active.

    The state the USSD flow leaves somebody in while the callback has not
    landed -- which, on this deployment, can be indefinitely.
    """
    from api.models import SubscriptionTier
    from api.models.subscription import SubscriptionPlan

    user = User.objects.create_user(username='awaiting', password='x')
    tier = SubscriptionTier.objects.filter(is_active=True).first()
    SubscriptionPlan.objects.create(
        user=user,
        tier=tier,
        status='pending',
        duration_type=getattr(tier, 'duration_type', 'daily'),
        start_date=timezone.now(),
        end_date=timezone.now() + timedelta(days=1),
    )
    return user


@pytest.fixture
def somebody_elses_post(db):
    author = User.objects.create_user(username='author', password='x')
    Subscription.objects.update_or_create(
        user=author,
        defaults={'plan': 'pro', 'expires_at': timezone.now() + timedelta(days=30)},
    )
    return Reel.objects.create(user=author, caption='a post', processed=True)


# ── calling the endpoints ───────────────────────────────────────────────────


def post_media(user, upload):
    from api.views.core import create_post

    request = factory.post('/posts/create/', {'caption': 'hello', 'file': upload})
    force_authenticate(request, user=user)
    return create_post(request)


def image(name='p.jpg'):
    return SimpleUploadedFile(name, jpeg_bytes(), content_type='image/jpeg')


def video(name='v.mp4'):
    return SimpleUploadedFile(name, MP4, content_type='video/mp4')


def act_on(user, reel, action):
    """Like, share or comment on `reel` as `user`."""
    from api.views.core import ReelViewSet

    bodies = {'vote': {}, 'share': {}, 'comments': {'text': 'nice'}}
    request = factory.post(f'/reels/{reel.pk}/{action}/', bodies[action])
    force_authenticate(request, user=user)
    view = ReelViewSet.as_view({'post': action})
    return view(request, pk=str(reel.pk))


def enter_campaign(user):
    from api.models.campaign import Campaign
    from api.views.campaign_user import create_campaign_post

    campaign = Campaign.objects.create(
        title='Sprint',
        campaign_type='daily',
        status='active',
        start_date=timezone.now() - timedelta(hours=1),
        entry_deadline=timezone.now() + timedelta(hours=1),
    )
    request = factory.post(
        '/campaigns/posts/create/', {'campaign_id': campaign.id, 'media': image()}
    )
    force_authenticate(request, user=user)
    return create_campaign_post(request)


def encrypted_post(view, user, path, body, keys):
    """POST to an @encrypted_endpoint, with the header it requires.

    JSON, not multipart: these endpoints negotiate an encrypted JSON body and
    answer 415 to a form post.
    """
    _server_public, public, _private = keys
    request = factory.post(path, body, format='json', HTTP_X_CLIENT_PUBLIC_KEY=public)
    force_authenticate(request, user=user)
    return view(request)


def refused_for_subscription(response):
    """A refusal the client can act on: 403 and the agreed code."""
    if response.status_code != 403:
        return False
    body = response.data or {}
    return body.get('code') == SUBSCRIPTION_REQUIRED_CODE


# ── what a non-subscriber may still do ──────────────────────────────────────


def test_a_non_subscriber_can_browse(nobody, somebody_elses_post):
    """Browsing is how somebody decides to subscribe. It stays open."""
    from api.views.core import ReelViewSet

    request = factory.get('/reels/')
    force_authenticate(request, user=nobody)
    response = ReelViewSet.as_view({'get': 'list'})(request)

    assert response.status_code == 200


def test_a_non_subscriber_can_view_a_post(nobody, somebody_elses_post):
    from api.views.core import ReelViewSet

    request = factory.get(f'/reels/{somebody_elses_post.pk}/')
    force_authenticate(request, user=nobody)
    response = ReelViewSet.as_view({'get': 'retrieve'})(request, pk=str(somebody_elses_post.pk))

    assert response.status_code == 200


def test_a_non_subscriber_can_read_comments(nobody, somebody_elses_post):
    """Reading is not commenting."""
    from api.views.core import ReelViewSet

    request = factory.get(f'/reels/{somebody_elses_post.pk}/comments/')
    force_authenticate(request, user=nobody)
    response = ReelViewSet.as_view({'get': 'comments'})(request, pk=str(somebody_elses_post.pk))

    assert response.status_code == 200


def test_an_anonymous_visitor_can_browse(somebody_elses_post):
    """Signing up is allowed, so the feed has to be visible before there is
    an account at all."""
    from api.views.core import ReelViewSet

    response = ReelViewSet.as_view({'get': 'list'})(factory.get('/reels/'))

    assert response.status_code == 200


# ── what a non-subscriber may not do ────────────────────────────────────────


def test_a_non_subscriber_cannot_post_an_image(nobody):
    """The gap: only video was gated, so images went through."""
    response = post_media(nobody, image())

    assert refused_for_subscription(response), response.data


def test_a_non_subscriber_cannot_upload_a_video(nobody):
    response = post_media(nobody, video())

    assert refused_for_subscription(response), response.data


def test_a_non_subscriber_cannot_like(nobody, somebody_elses_post):
    response = act_on(nobody, somebody_elses_post, 'vote')

    assert refused_for_subscription(response), response.data


def test_a_non_subscriber_cannot_share(nobody, somebody_elses_post):
    response = act_on(nobody, somebody_elses_post, 'share')

    assert refused_for_subscription(response), response.data


def test_a_non_subscriber_cannot_comment(nobody, somebody_elses_post):
    response = act_on(nobody, somebody_elses_post, 'comments')

    assert refused_for_subscription(response), response.data


def test_a_non_subscriber_cannot_enter_a_campaign(nobody):
    response = enter_campaign(nobody)

    assert refused_for_subscription(response), response.data


# ── a refusal changes nothing ───────────────────────────────────────────────


def test_a_refused_like_is_not_recorded(nobody, somebody_elses_post):
    """Not shown as successful, and not half-done either."""
    from api.models import Vote

    before = somebody_elses_post.votes

    act_on(nobody, somebody_elses_post, 'vote')

    somebody_elses_post.refresh_from_db()
    assert somebody_elses_post.votes == before
    assert not Vote.objects.filter(user=nobody, reel=somebody_elses_post).exists()


def test_a_refused_comment_is_not_recorded(nobody, somebody_elses_post):
    from api.models import Comment

    act_on(nobody, somebody_elses_post, 'comments')

    assert not Comment.objects.filter(user=nobody, reel=somebody_elses_post).exists()


def test_a_refused_share_does_not_move_the_count(nobody, somebody_elses_post):
    before = somebody_elses_post.shares

    act_on(nobody, somebody_elses_post, 'share')

    somebody_elses_post.refresh_from_db()
    assert somebody_elses_post.shares == before


def test_a_refused_post_creates_nothing(nobody):
    post_media(nobody, image())

    assert not Reel.objects.filter(user=nobody).exists()


def test_a_refusal_costs_no_coins(nobody, somebody_elses_post):
    """The welcome bonus is still there afterwards.

    A refused action that charged would be the worst of both: no like, and
    the coins gone.
    """
    from api.models.contest import UserCoinBalance

    balance, _ = UserCoinBalance.objects.get_or_create(user=nobody)
    balance.refresh_from_db()
    before = balance.balance

    act_on(nobody, somebody_elses_post, 'vote')
    act_on(nobody, somebody_elses_post, 'share')
    act_on(nobody, somebody_elses_post, 'comments')
    post_media(nobody, image())

    balance.refresh_from_db()
    assert balance.balance == before


def test_coins_alone_do_not_buy_the_action(nobody, somebody_elses_post):
    """The heart of the gap.

    A new account gets welcome-bonus coins, so the engagement charge was
    never a gate -- it prices an action, it does not decide who may take it.
    Plenty of coins, still refused.
    """
    from api.models.contest import UserCoinBalance

    balance, _ = UserCoinBalance.objects.get_or_create(user=nobody)
    balance.add_purchased(10_000, payment_method='telebirr')

    assert refused_for_subscription(act_on(nobody, somebody_elses_post, 'vote'))


# ── the subscriber states ───────────────────────────────────────────────────


def test_an_active_subscriber_may_act(subscriber, somebody_elses_post):
    """The gate must not refuse everybody."""
    assert has_active_subscription(subscriber)
    assert subscriber_action_refusal(subscriber, 'like') is None

    response = act_on(subscriber, somebody_elses_post, 'vote')

    assert response.status_code == 200, response.data


def test_an_active_subscriber_may_post(subscriber):
    response = post_media(subscriber, image())

    assert response.status_code in (200, 201), response.data


def test_an_expired_subscriber_is_refused(expired, somebody_elses_post):
    """An end date in the past is not a subscription, whatever the status
    column says."""
    assert not has_active_subscription(expired)
    assert refused_for_subscription(act_on(expired, somebody_elses_post, 'vote'))


def test_a_pending_subscriber_is_refused(pending, somebody_elses_post):
    """Paid but unconfirmed is not yet subscribed.

    This is the state a USSD payment leaves somebody in while the callback
    has not arrived -- which on this deployment can be indefinite -- so it
    must not read as access.
    """
    assert not has_active_subscription(pending)
    assert refused_for_subscription(act_on(pending, somebody_elses_post, 'vote'))


def test_a_pending_subscriber_cannot_post(pending):
    assert refused_for_subscription(post_media(pending, image()))


# ── insufficient balance ────────────────────────────────────────────────────


def test_a_subscriber_with_no_coins_keeps_their_access(subscriber, somebody_elses_post):
    """Requirement: a subscriber may continue accessing the platform.

    Running out of coins is not losing your subscription. Browsing, viewing
    and reading all still work.
    """
    from api.models.contest import UserCoinBalance
    from api.views.core import ReelViewSet

    balance, _ = UserCoinBalance.objects.get_or_create(user=subscriber)
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        balance=0,
        earned_balance=0,
        bonus_balance=0,
        telebirr_purchased_balance=0,
        airtime_purchased_balance=0,
        purchased_balance=0,
    )

    request = factory.get('/reels/')
    force_authenticate(request, user=subscriber)

    assert ReelViewSet.as_view({'get': 'list'})(request).status_code == 200
    assert has_active_subscription(subscriber)


def test_a_chargeable_action_is_refused_until_they_recharge(subscriber, somebody_elses_post):
    """And refused for the right reason: money, not access.

    The two refusals are different codes so the client sends the person to
    the coin shop rather than the subscribe page.
    """
    from api.models.contest import UserCoinBalance

    balance, _ = UserCoinBalance.objects.get_or_create(user=subscriber)
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        balance=0,
        earned_balance=0,
        bonus_balance=0,
        telebirr_purchased_balance=0,
        airtime_purchased_balance=0,
        purchased_balance=0,
    )

    response = act_on(subscriber, somebody_elses_post, 'vote')

    assert response.status_code == 400, response.data
    assert (response.data or {}).get('code') != SUBSCRIPTION_REQUIRED_CODE


def test_recharging_restores_the_action(subscriber, somebody_elses_post):
    from api.models.contest import UserCoinBalance

    balance, _ = UserCoinBalance.objects.get_or_create(user=subscriber)
    UserCoinBalance.objects.filter(pk=balance.pk).update(
        balance=0,
        earned_balance=0,
        bonus_balance=0,
        telebirr_purchased_balance=0,
        airtime_purchased_balance=0,
        purchased_balance=0,
    )
    balance.refresh_from_db()
    assert act_on(subscriber, somebody_elses_post, 'vote').status_code == 400

    balance.add_purchased(500, payment_method='telebirr')

    assert act_on(subscriber, somebody_elses_post, 'vote').status_code == 200


# ── the refusal the client branches on ──────────────────────────────────────


@pytest.mark.parametrize('action', ['post', 'video', 'like', 'share', 'comment', 'campaign'])
def test_every_action_has_its_own_wording(action):
    """'An active subscription is required to post videos' shown to somebody
    who tapped Like is how an app comes to look broken."""
    from api.services.subscription_access import SUBSCRIBER_ACTIONS

    assert SUBSCRIBER_ACTIONS[action]


def test_the_refusal_names_the_action_that_was_refused(nobody):
    refusal = subscriber_action_refusal(nobody, 'like')

    assert refusal['code'] == SUBSCRIPTION_REQUIRED_CODE
    assert refusal['action'] == 'like'
    assert 'like' in refusal['message'].lower()


def test_the_code_is_the_same_everywhere(nobody, somebody_elses_post):
    """One code across every refusal, so the client has one branch rather
    than a list of endpoints to remember."""
    responses = [
        post_media(nobody, image()),
        act_on(nobody, somebody_elses_post, 'vote'),
        act_on(nobody, somebody_elses_post, 'share'),
        act_on(nobody, somebody_elses_post, 'comments'),
        enter_campaign(nobody),
    ]

    for response in responses:
        assert refused_for_subscription(response), response.data


def test_a_refusal_is_never_reported_as_success(nobody, somebody_elses_post):
    """The frontend requirement, checked at the source: nothing in a refusal
    says it worked."""
    for response in (
        post_media(nobody, image()),
        act_on(nobody, somebody_elses_post, 'vote'),
        act_on(nobody, somebody_elses_post, 'comments'),
    ):
        body = response.data or {}
        assert response.status_code == 403
        assert body.get('success') is not True


# ── calling the API directly ────────────────────────────────────────────────


def test_the_gate_is_in_the_api_not_the_client(nobody, somebody_elses_post):
    """Every refusal above came from calling the view directly, with no
    client involved. That is the requirement: the restriction has to hold
    for somebody with curl."""
    assert refused_for_subscription(act_on(nobody, somebody_elses_post, 'vote'))


def test_a_write_still_requires_signing_in(somebody_elses_post):
    """Authentication first, subscription second."""
    from api.views.core import ReelViewSet

    request = factory.post(f'/reels/{somebody_elses_post.pk}/vote/')
    response = ReelViewSet.as_view({'post': 'vote'})(request, pk=str(somebody_elses_post.pk))

    assert response.status_code in (401, 403)


def test_no_write_endpoint_takes_the_client_s_word_for_the_subscription(
    nobody, somebody_elses_post
):
    """A request cannot declare itself subscribed."""
    from api.views.core import ReelViewSet

    request = factory.post(
        f'/reels/{somebody_elses_post.pk}/vote/',
        {'has_subscription': True, 'is_subscriber': True, 'subscription_status': 'active'},
    )
    force_authenticate(request, user=nobody)
    response = ReelViewSet.as_view({'post': 'vote'})(request, pk=str(somebody_elses_post.pk))

    assert refused_for_subscription(response), response.data


# ── the second doors ────────────────────────────────────────────────────────
#
# Each of these charges or creates the same thing as an endpoint that was
# already gated, and none of them checked. Found by listing every
# charge_engagement call site and comparing it against every gate -- which is
# how they should have been found the first time.


def test_a_non_subscriber_cannot_share_by_picking_recipients(nobody, somebody_elses_post):
    """`share_with` sends a post as a DM and charges the `share` price.

    Tapping Share was refused; choosing recipients was not, so the gate came
    down to which button the client happened to call.
    """
    from api.views.core import ReelViewSet

    other = User.objects.create_user(username='recipient', password='x')
    request = factory.post(f'/reels/{somebody_elses_post.pk}/share_with/', {'user_ids': [other.pk]})
    force_authenticate(request, user=nobody)
    response = ReelViewSet.as_view({'post': 'share_with'})(request, pk=str(somebody_elses_post.pk))

    assert refused_for_subscription(response), response.data


def test_a_refused_direct_share_sends_no_messages(nobody, somebody_elses_post):
    from api.models.messaging import Message
    from api.views.core import ReelViewSet

    other = User.objects.create_user(username='recipient2', password='x')
    request = factory.post(f'/reels/{somebody_elses_post.pk}/share_with/', {'user_ids': [other.pk]})
    force_authenticate(request, user=nobody)
    ReelViewSet.as_view({'post': 'share_with'})(request, pk=str(somebody_elses_post.pk))

    assert not Message.objects.filter(sender=nobody).exists()


def test_a_non_subscriber_cannot_send_a_gift(nobody, encrypted_client_keys):
    """The web app's own engagement gate lists gifts as subscriber-only; the
    server did not."""
    from api.views.contest import gift_creator

    creator = User.objects.create_user(username='a_creator', password='x')
    response = encrypted_post(
        gift_creator,
        nobody,
        '/gift-creator/',
        {'recipient_id': creator.pk, 'coins': 10},
        encrypted_client_keys,
    )

    assert refused_for_subscription(response), response.data


def test_a_non_subscriber_cannot_send_a_named_gift(nobody, encrypted_client_keys):
    from api.views.contest import send_gift

    recipient = User.objects.create_user(username='gift_target', password='x')
    response = encrypted_post(
        send_gift,
        nobody,
        '/send-gift/',
        {'recipient_username': recipient.username, 'amount': 10},
        encrypted_client_keys,
    )

    assert refused_for_subscription(response), response.data


def test_a_refused_gift_moves_no_coins(nobody, encrypted_client_keys):
    from api.models.contest import UserCoinBalance
    from api.views.contest import gift_creator

    creator = User.objects.create_user(username='unpaid_creator', password='x')
    balance, _ = UserCoinBalance.objects.get_or_create(user=nobody)
    balance.add_purchased(1_000, payment_method='telebirr')
    balance.refresh_from_db()
    before = balance.balance

    encrypted_post(
        gift_creator,
        nobody,
        '/gift-creator/',
        {'recipient_id': creator.pk, 'coins': 100},
        encrypted_client_keys,
    )

    balance.refresh_from_db()
    assert balance.balance == before


def test_a_non_subscriber_cannot_comment_through_the_comment_viewset(
    nobody, somebody_elses_post, encrypted_client_keys
):
    """The reel's `comments` action was gated; this viewset is a second way
    to create exactly the same row."""
    from api.models import Comment
    from api.views.extended import CommentViewSet

    response = encrypted_post(
        CommentViewSet.as_view({'post': 'create'}),
        nobody,
        '/comments/',
        {'reel': somebody_elses_post.pk, 'text': 'hi'},
        encrypted_client_keys,
    )

    assert refused_for_subscription(response), response.data
    assert not Comment.objects.filter(user=nobody).exists()


def test_a_non_subscriber_cannot_reply_to_a_comment(
    nobody, somebody_elses_post, encrypted_client_keys
):
    from api.models import Comment, CommentReply
    from api.views.extended import CommentReplyViewSet

    comment = Comment.objects.create(
        user=somebody_elses_post.user, reel=somebody_elses_post, text='first'
    )
    response = encrypted_post(
        CommentReplyViewSet.as_view({'post': 'create'}),
        nobody,
        '/comment-replies/',
        {'comment': comment.pk, 'text': 'me too'},
        encrypted_client_keys,
    )

    assert refused_for_subscription(response), response.data
    assert not CommentReply.objects.filter(user=nobody).exists()


def test_a_subscriber_gets_past_the_comment_viewset_gate(
    subscriber, somebody_elses_post, encrypted_client_keys
):
    """The gate must not close the door on people who paid.

    What is asserted is that they are not refused *for want of a
    subscription*. Going further would mean encrypting the body for real --
    this viewset decrypts after the gate, so a plain body fails later on its
    own terms, which says nothing about access. The refusals above are the
    ones that matter here; that a subscriber can comment end to end is
    covered by test_an_active_subscriber_may_act.
    """
    from api.views.extended import CommentViewSet

    response = encrypted_post(
        CommentViewSet.as_view({'post': 'create'}),
        subscriber,
        '/comments/',
        {'reel': somebody_elses_post.pk, 'text': 'hello'},
        encrypted_client_keys,
    )

    assert not refused_for_subscription(response), response.data


#: Endpoints that spend a user's coins without needing a subscription, and
#: why each one is allowed to.
#:
#: Everything else that spends coins is a contribution -- posting, voting,
#: gifting, boosting -- and needs a plan. An entry here is a deliberate
#: exception, not a a place to park an ungated endpoint.
SPEND_WITHOUT_SUBSCRIPTION = {
    # Buying access itself. Gated by coin_purchase_refusal instead, which
    # answers a different question: you may buy coins with a plan, and this
    # is how you get one.
    'subscription_upgrade',
    # Converting points back to coins and withdrawing are about money the
    # user already earned, not about contributing.
    'reinvest',
    # The system taking back coins it credited for a payment that later
    # failed (_rollback_one_off_coins, inside the telebirr webhook). No user
    # request, so no subscription question -- asking one here would mean a
    # lapsed subscriber kept coins they never paid for.
    'rollback',
}


def spend_sites(source):
    """Every coin-spending call in a module, by its transaction type."""
    import re

    found = set()
    for pattern in (
        r"spend_coins\(\s*[^,)]+,\s*'([a-z_]+)'",
        r"charge_engagement\(\s*request\.user,\s*[^,]+,\s*'([a-z_]+)'",
    ):
        found.update(re.findall(pattern, source))
    return found


def test_every_module_that_charges_also_gates():
    """The check that would have caught all of these at once.

    The first version of this test read only api/views/core.py, so it passed
    while four charged endpoints in three other modules stayed open --
    vote_grand_finale, boost_post, purchase_extra_entry and a third gift
    path in gamification.py. Scoping a guard to the file you happen to be
    editing is how the next one gets missed too, so it now sweeps every view
    module.

    Asserted against the source because the failure mode is a *new* endpoint
    charging without gating, which no runtime test can anticipate.
    """
    from pathlib import Path

    from api import views

    views_dir = Path(views.__file__).parent
    offenders = []

    for path in sorted(views_dir.glob('*.py')):
        source = path.read_text(encoding='utf-8')
        spends = spend_sites(source) - SPEND_WITHOUT_SUBSCRIPTION
        if not spends:
            continue
        if 'subscriber_action_refusal' in source or '_video_subscription_refusal' in source:
            continue
        offenders.append(f'{path.name} spends coins for {sorted(spends)} with no subscription gate')

    assert not offenders, '\n'.join(offenders)


def test_every_charged_action_in_the_feed_is_gated():
    """The per-action count for the feed endpoints specifically.

    A module-level check passes as soon as *one* gate exists in the file;
    this catches a second charged action added beside a gated one, which is
    exactly what share_with was.
    """
    from pathlib import Path

    from api.views import core

    source = Path(core.__file__).read_text(encoding='utf-8')
    charge_sites = source.count('charge_engagement(request.user')
    gate_sites = source.count('subscriber_action_refusal(request.user')

    assert gate_sites >= charge_sites, (
        f'{charge_sites} charged actions but only {gate_sites} gated: '
        'an endpoint charges for engagement without checking the subscription'
    )


# ── the contest and gamification doors ──────────────────────────────────────
#
# Four more charged endpoints in three modules the first sweep never looked
# at, because that sweep was scoped to api/views/core.py.


def test_a_non_subscriber_cannot_vote_in_the_grand_finale(nobody, encrypted_client_keys):
    """A vote is a vote. The requirement names 'Like/vote' among what a
    non-subscriber may not do, and this one charges coins for it."""
    from api.views.contest import vote_grand_finale

    response = encrypted_post(
        vote_grand_finale,
        nobody,
        '/vote-grand-finale/',
        {'entry_id': 1, 'coins': 10},
        encrypted_client_keys,
    )

    assert refused_for_subscription(response), response.data


def test_a_non_subscriber_cannot_gift_through_gamification(nobody, encrypted_client_keys):
    """The third gift path, found only by sweeping every module."""
    from api.views.gamification import send_coin_gift

    recipient = User.objects.create_user(username='gam_target', password='x')
    response = encrypted_post(
        send_coin_gift,
        nobody,
        '/send-coin-gift/',
        {'recipient_username': recipient.username, 'amount': 10},
        encrypted_client_keys,
    )

    assert refused_for_subscription(response), response.data


def test_a_non_subscriber_cannot_boost_a_post(nobody, somebody_elses_post, encrypted_client_keys):
    from api.views.contest import boost_post

    response = encrypted_post(
        boost_post,
        nobody,
        '/boost-post/',
        {'reel_id': somebody_elses_post.pk},
        encrypted_client_keys,
    )

    assert refused_for_subscription(response), response.data


def test_a_non_subscriber_cannot_buy_an_extra_entry(nobody, encrypted_client_keys):
    """Buying the right to post again is subject to the rule about posting."""
    from api.views.contest import purchase_extra_entry

    response = encrypted_post(
        purchase_extra_entry,
        nobody,
        '/purchase-extra-entry/',
        {},
        encrypted_client_keys,
    )

    assert refused_for_subscription(response), response.data


def test_none_of_these_refusals_spend_coins(nobody, somebody_elses_post, encrypted_client_keys):
    """A refusal costs nothing, on every one of these paths."""
    from api.models.contest import UserCoinBalance
    from api.views.contest import boost_post, purchase_extra_entry, vote_grand_finale
    from api.views.gamification import send_coin_gift

    balance, _ = UserCoinBalance.objects.get_or_create(user=nobody)
    balance.add_purchased(5_000, payment_method='telebirr')
    balance.refresh_from_db()
    before = balance.balance

    recipient = User.objects.create_user(username='untouched', password='x')
    encrypted_post(
        vote_grand_finale,
        nobody,
        '/vote-grand-finale/',
        {'entry_id': 1, 'coins': 10},
        encrypted_client_keys,
    )
    encrypted_post(
        send_coin_gift,
        nobody,
        '/send-coin-gift/',
        {'recipient_username': recipient.username, 'amount': 10},
        encrypted_client_keys,
    )
    for view, body in (
        (boost_post, {'reel_id': somebody_elses_post.pk}),
        (purchase_extra_entry, {}),
    ):
        encrypted_post(view, nobody, '/x/', body, encrypted_client_keys)

    balance.refresh_from_db()
    assert balance.balance == before
