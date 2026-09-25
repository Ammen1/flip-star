"""
How long a video this user may post.

    standard subscriber          60 seconds
    coin buyer / on-demand      120 seconds

The second is unlocked by having bought coins. Everything else about posting
a video is unchanged: an active subscription is still required
(api/services/subscription_access.py), and a video of 60 seconds or more is
still charged the long-video price (api/services/post_pricing.py). This
module adds only the ceiling.

Why the two rules are not the same rule
---------------------------------------
Pricing already treats 60 seconds as the boundary between bands, and it is
tempting to read the new limit as "the long-video band requires a purchase".
They are different questions and are kept apart:

* pricing asks *what does this cost*, measured after the fact by the worker;
* this asks *may this exist at all*, and the answer decides whether the post
  is published or rejected.

A standard subscriber uploading 90 seconds is not someone who owes 100
coins. They are someone whose video will not be published, and telling them
that before they wait for processing is the difference between a limit and a
surprise.

Where it is enforced
--------------------
In the worker, against the duration ffprobe actually measured
(api/tasks/media.py). That is the only place a real duration exists: the
upload request deliberately does not run FFmpeg, and the request has no
duration to check that a client could not have made up. A caller posting
straight to the API with ``duration=10`` in the body changes nothing,
because nothing reads it -- the file is measured, not believed.

The limit is also published to clients so the create screen can say "up to
60 seconds" and refuse early. That is a courtesy, not the rule: the client's
copy can be stale, edited, or simply not used.
"""

from __future__ import annotations

from django.conf import settings

#: What a subscription alone allows.
STANDARD_MAX_SECONDS = 60

#: What a coin purchase unlocks.
EXTENDED_MAX_SECONDS = 120


def qualifying_purchase_minimum() -> int:
    """Coins that must have been bought to unlock the longer limit.

    Configurable because "the required qualifying coin purchase" is a
    commercial decision that will be tuned, and tuning it should not be a
    deploy. Zero -- the default -- means any completed purchase qualifies,
    which is the plain reading of "coin buyer".
    """
    return int(getattr(settings, 'VIDEO_EXTENDED_MIN_PURCHASED_COINS', 0) or 0)


def has_qualifying_purchase(user) -> bool:
    """Whether this user has bought coins.

    Counted over every purchase they have ever made, not their balance:
    spending the coins does not stop somebody having been a coin buyer, and
    a limit that rose and fell with a balance would be incomprehensible to
    the person it applied to.
    """
    if user is None or not getattr(user, 'is_authenticated', True):
        return False

    from api.models.contest import CoinTransaction

    purchases = CoinTransaction.objects.filter(user=user, transaction_type='purchase')

    minimum = qualifying_purchase_minimum()
    if minimum <= 0:
        return purchases.exists()

    from django.db.models import Sum

    # `coins`, not `amount`: CoinTransaction records the coins moved, and
    # amount_etb is what was paid for them. Summing the wrong one would
    # compare a birr figure against a coin threshold.
    bought = purchases.aggregate(total=Sum('coins'))['total'] or 0
    return bought >= minimum


def has_ondemand_subscription(user) -> bool:
    """Whether they hold an on-demand plan.

    The on-demand tier buys its coins outright rather than receiving a daily
    gift (api/services/subscription_tiers.py), so its holders are coin
    buyers by definition and get the longer limit whether or not a purchase
    row happens to exist yet.
    """
    if user is None or not getattr(user, 'is_authenticated', True):
        return False

    from api.models.subscription import SubscriptionPlan

    return SubscriptionPlan.objects.filter(
        user=user, status='active', duration_type='ondemand'
    ).exists()


def max_video_seconds(user) -> int:
    """The longest video this user may post, in seconds.

    Never above the deployment's own ceiling: MEDIA_MAX_VIDEO_SECONDS is
    what the storage and encoding budget can take, and no entitlement
    overrides it.
    """
    ceiling = int(getattr(settings, 'MEDIA_MAX_VIDEO_SECONDS', EXTENDED_MAX_SECONDS))

    if has_qualifying_purchase(user) or has_ondemand_subscription(user):
        return min(EXTENDED_MAX_SECONDS, ceiling)

    return min(STANDARD_MAX_SECONDS, ceiling)


def exceeds_limit(duration, user) -> bool:
    """Is this measured duration longer than the user may post?

    Inclusive of the limit: 60.0 seconds is allowed for a standard
    subscriber, 60.01 is not. The same direction as the pricing boundary in
    post_pricing.py, so "60 seconds" means one thing across the product.

    An unmeasured duration is not over the limit. The worker rejects on what
    it measured; refusing a video because probing failed would turn an
    encoding problem into an accusation.
    """
    if not duration:
        return False
    try:
        return float(duration) > max_video_seconds(user)
    except (TypeError, ValueError):
        return False


def limits_for(user) -> dict:
    """What the create screen needs to show, and why.

    `extended_unlocked` rather than only the number, so the page can say
    what buying coins would get instead of silently showing a smaller limit
    than somebody else has.
    """
    allowed = max_video_seconds(user)
    unlocked = allowed >= EXTENDED_MAX_SECONDS

    return {
        'max_video_seconds': allowed,
        'standard_max_seconds': STANDARD_MAX_SECONDS,
        'extended_max_seconds': EXTENDED_MAX_SECONDS,
        'extended_unlocked': unlocked,
        'extended_requires': (None if unlocked else 'Buy coins to post videos up to 2 minutes.'),
    }


def too_long_message(user) -> str:
    """What somebody is told when their video is over the limit.

    Says the limit and, when it is the shorter one, how it is raised --
    a refusal that does not say what would have worked is just a wall.
    """
    allowed = max_video_seconds(user)
    if allowed >= EXTENDED_MAX_SECONDS:
        return f'Videos can be up to {allowed} seconds long.'
    return (
        f'Videos can be up to {allowed} seconds on your current plan. '
        f'Buy coins to post videos up to {EXTENDED_MAX_SECONDS} seconds.'
    )
